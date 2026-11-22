# Thực hành tổng hợp: quan sát type erasure và bridge method bằng `javap`

## Mục tiêu của phòng thực hành

Trong Java generics, mã nguồn nhìn thấy các kiểu như `Store<String>` và `NumberWorker<Integer>`, nhưng phần lớn thông tin đối số kiểu được **xóa kiểu** (*type erasure*) khi biên dịch. Khi lớp con ghi đè một phương thức generic, descriptor JVM của phương thức chuyên biệt có thể khác descriptor phương thức cha. Trình biên dịch Java có thể sinh một **bridge method** để lời gọi đa hình vẫn hoạt động.

Bài thực hành này đưa ra một chương trình Java 17 chạy được, sau đó kiểm chứng **từng nhận định bằng tệp `.class`**, không chỉ bằng suy đoán từ mã nguồn. Sau khi hoàn thành, bạn có thể:

- Dự đoán erasure của `T` không giới hạn và `T extends Number`.
- Dùng `javap -p -s` để đối chiếu JVM descriptor của field/phương thức với chữ ký ở Java source.
- Dùng `javap -p -c` để lần theo bytecode: `checkcast`, `invokevirtual`, `invokespecial` và `areturn`.
- Dùng `javap -p -v` xác nhận cờ `ACC_BRIDGE` và `ACC_SYNTHETIC` của phương thức do compiler tạo.
- Đối chiếu hai kiểu bridge: `set(Object)` có cast đầu vào, `get():Object` chuyển tiếp kiểu trả về.
- Phân biệt cầu nối do `Object` erasure với cầu nối dùng `Number` từ upper bound.
- Sử dụng reflection `Method.isBridge()` để xác minh ở thời gian chạy và giải thích tình huống raw type gây `ClassCastException`.

**Yêu cầu:** Java 17 trở lên, có `javac`, `java` và `javap` cùng một bộ JDK. Không cần Gradle, Maven hoặc thư viện ngoài.

## 1. Dự đoán trước khi mở bytecode

Hãy xem ba mối quan hệ kiểu trong một bài toán:

```java
class Store<T> {
    public void set(T item) { /* ... */ }
    public T get() { /* ... */ }
}

class StringStore extends Store<String> {
    @Override public void set(String item) { /* ... */ }
    @Override public String get() { /* ... */ }
}

class NumberWorker<T extends Number> {
    public T next(T value) { return value; }
}

class IntegerWorker extends NumberWorker<Integer> {
    @Override public Integer next(Integer value) { return value + 1; }
}
```

Đây là **trích yếu dùng để phân tích chữ ký**; chương trình đầy đủ có thể biên dịch nằm ở phần tiếp theo.

Trước khi chạy lệnh, hãy tự dự đoán:

1. Sau type erasure, `Store<T>.set(T)` nhận `T`, `Object` hay `String`?
2. `Store<T>.get()` trả về kiểu gì trong JVM descriptor?
3. Trong `StringStore`, compiler cần thêm phương thức nào để kết nối lời gọi qua `Store<String>` với phương thức ghi đè nhận `String`?
4. Nếu cầu nối `set(Object)` nhận thực tế một `Integer`, điều gì xảy ra?
5. Với `NumberWorker<T extends Number>`, upper bound có khiến erasure của `T` khác `Object` không?

Giữ các dự đoán này để đối chiếu với `javap` và kết quả chạy. Đó là bước quan trọng nhất của một bài lab: **mỗi kết luận đều phải có bằng chứng quan sát**.

## 2. Tạo một chương trình có đầy đủ trường hợp kiểm chứng

Tạo tệp đúng tên **`ErasureBridgeLab.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class ErasureBridgeLab {
    static class Store<T> {
        private T item;

        public void set(T item) {
            this.item = item;
        }

        public T get() {
            return item;
        }
    }

    static final class StringStore extends Store<String> {
        @Override
        public void set(String item) {
            super.set(item.trim());
        }

        @Override
        public String get() {
            return super.get();
        }
    }

    static class NumberWorker<T extends Number> {
        public T next(T value) {
            return value;
        }
    }

    static final class IntegerWorker extends NumberWorker<Integer> {
        @Override
        public Integer next(Integer value) {
            return value + 1;
        }
    }

    static <T> T echo(T item) {
        return item;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Store<String> store = new StringStore();
        store.set("  java  ");
        System.out.println("stored: " + store.get());
        System.out.println("runtime: " + store.getClass().getSimpleName());

        Method concrete = StringStore.class
                .getDeclaredMethod("set", String.class);
        Method bridge = StringStore.class
                .getDeclaredMethod("set", Object.class);
        System.out.println("set(String) bridge: " + concrete.isBridge());
        System.out.println("set(Object) bridge: " + bridge.isBridge());
        System.out.println("set(Object) synthetic: " + bridge.isSynthetic());

        List<String> bridges = Arrays
                .stream(StringStore.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .map(Method::getName)
                .sorted()
                .toList();
        System.out.println("StringStore bridges: " + bridges);

        NumberWorker<Integer> worker = new IntegerWorker();
        System.out.println("bounded: " + worker.next(7));
        System.out.println("echo: " + echo("ok"));

        Store raw = new StringStore();
        try {
            raw.set(123);
        } catch (ClassCastException ex) {
            System.out.println("raw failure: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Các lớp `Store`, `StringStore`, `NumberWorker` và `IntegerWorker` ở đây là **static nested classes**. `javac` sẽ tạo các class file cho từng lớp lồng; tên nhị phân có `$` giữa tên lớp ngoài và lớp trong. Việc dùng cùng một tệp giúp tái tạo tất cả thí nghiệm với một lệnh biên dịch.

**Chi tiết có chủ đích:**

- `Store<T>` chứa field `T item`, phương thức nhận `T` và phương thức trả `T`: quan sát được erasure ở ba vị trí.
- `StringStore` ghi đè cả `set(String)` và `get():String`: ta sẽ thấy **hai bridge** với hành vi khác nhau.
- `NumberWorker<T extends Number>` có upper bound: bài test xác nhận bridge dùng `Number` chứ không mặc định dùng `Object`.
- `echo(T)` là generic method độc lập với các lớp generic: descriptor chứng minh type erasure cũng áp dụng cho tham số kiểu khai báo ở cấp method.
- Đoạn raw `Store` cố tình tạo cảnh báo/lỗi runtime để phơi bày nơi compiler mất khả năng bảo vệ kiểu.
- Reflection dùng `getDeclaredMethod` với tham số cụ thể, còn danh sách bridge được **sort theo tên** để stdout không phụ thuộc thứ tự `getDeclaredMethods()`.

## 3. Biên dịch và chạy để kiểm tra hành vi

Trong thư mục có `ErasureBridgeLab.java`, chạy:

```bash
javac -Xlint:rawtypes -Xlint:unchecked ErasureBridgeLab.java
java ErasureBridgeLab
```

**Stdout đã kiểm chứng trên Java 17+**:

```text
stored: java
runtime: StringStore
set(String) bridge: false
set(Object) bridge: true
set(Object) synthetic: true
StringStore bridges: [get, set]
bounded: 8
echo: ok
raw failure: ClassCastException
```

`javac` còn phát **hai cảnh báo** trong ví dụ: một `[rawtypes]` ở `Store raw` và một `[unchecked]` ở `raw.set(123)`. Đó là thông báo từ compiler, không phải stdout của `java ErasureBridgeLab`. Dòng `raw failure` do khối `catch` trong chương trình in ra.

Giải thích bước đầu:

- `store` được khai báo `Store<String>` nên compiler chỉ cho phép gọi `set` với `String` trên tham chiếu ấy.
- Instance thật được tạo bởi `new StringStore()`, vì vậy lời gọi đa hình đi tới logic của lớp con và xóa khoảng trắng bằng `trim()`.
- `set(String)` là phương thức do người viết khai báo; `set(Object)` mang tính **bridge** do compiler tạo.
- Cả `get` và `set` đều có bridge trong `StringStore`.
- `IntegerWorker.next(7)` tăng số từ `7` lên `8`.
- Raw type làm mất thông tin `String` ở nguồn; bridge cố ép `Integer` sang `String` và ném `ClassCastException`.

**Điều cần quan sát riêng:** Kết quả `runtime: StringStore` phản ánh **lớp thật của instance**, không phải chuỗi `Store<String>` tại compile time. Cùng một đối tượng có thể được giữ qua biến kiểu cha.

## 4. Tìm đúng class file và dùng `javap`

Sau khi biên dịch, các class file liên quan có tên nhị phân như:

```text
ErasureBridgeLab.class
ErasureBridgeLab$Store.class
ErasureBridgeLab$StringStore.class
ErasureBridgeLab$NumberWorker.class
ErasureBridgeLab$IntegerWorker.class
```

Đừng chỉ chạy `javap ErasureBridgeLab` rồi kết luận không có bridge: method được tạo nằm trong **class con** tương ứng.

Các lệnh quan sát:

```bash
javap -p -s 'ErasureBridgeLab$Store'
javap -p -s 'ErasureBridgeLab$StringStore'
javap -p -s 'ErasureBridgeLab$NumberWorker'
javap -p -s 'ErasureBridgeLab$IntegerWorker'
javap -p -s ErasureBridgeLab
```

Dấu nháy đơn quanh tên lớp có `$` hoạt động trong Bash và PowerShell, giúp shell không hiểu `$Store`, `$StringStore` là tên biến. Nếu chạy `javap` từ thư mục khác, thêm `-classpath <thư_mục_chứa_class>` và giữ đúng tên nhị phân.

Ba chế độ quan trọng:

| Lệnh | Mục đích |
| --- | --- |
| `javap -p -s` | Hiển thị mọi method/field và JVM **descriptor** |
| `javap -p -c` | Hiển thị instruction trong thân phương thức |
| `javap -p -v` | Hiển thị access flags, `Signature`, constant pool và metadata |

`javap -p` hiển thị cả thành viên private, giúp quan sát field `item`. `javap -s` cho biết descriptor chính xác; `javap -v` mới là cách rõ ràng để xem cờ cầu nối.

## 5. Thí nghiệm A — Type erasure của `Store<T>` không giới hạn

Source của lớp cha:

```java
static class Store<T> {
    private T item;
    public void set(T item) { this.item = item; }
    public T get() { return item; }
}
```

Đoạn này đã nằm trong chương trình đầy đủ ở phần 2. `T` không có `extends` nên upper bound hiệu dụng là `Object`.

Chạy:

```bash
javap -p -s 'ErasureBridgeLab$Store'
```

Trích kết quả **đã kiểm chứng**:

```text
class ErasureBridgeLab$Store<T> {
  private T item;
    descriptor: Ljava/lang/Object;

  public void set(T);
    descriptor: (Ljava/lang/Object;)V

  public T get();
    descriptor: ()Ljava/lang/Object;
}
```

Trong descriptor JVM:

- `Ljava/lang/Object;` là tham chiếu tới `java.lang.Object`.
- Phần trong dấu ngoặc `(...)` là kiểu tham số của phương thức.
- `V` là kiểu trả về `void`.
- `()Ljava/lang/Object;` nghĩa là method **không nhận tham số** và trả `Object`.

`javap` vẫn có thể in `T` trên dòng khai báo của lớp/phương thức vì class file giữ metadata **generic Signature** để công cụ và reflection đọc lại thông tin generic được khai báo. Nhưng descriptor chứa kiểu xóa đã cho thấy JVM biểu diễn phương thức ra sao.

Như vậy, `Store<String>` và `Store<Integer>` không cần các phiên bản runtime `Store` riêng cho `String` hay `Integer`. Runtime nhận những instance của lớp thật, còn trình biên dịch Java kiểm tra kiểu tham số generic và có thể chèn cast tại điểm dùng giá trị.

**Câu hỏi kiểm tra:** `Store<T>.get()` ở source trả `T`. Nếu một biến `Store<String>` gọi `get()`, biểu thức ở source được hiểu là `String`, nhưng descriptor `get` trong class cha là `()Ljava/lang/Object;`. Compiler có thể chèn `checkcast java/lang/String` tại vị trí cần dùng kết quả.

## 6. Thí nghiệm B — Quan sát hai bridge trong `StringStore`

`StringStore` khai báo:

```java
static final class StringStore extends Store<String> {
    @Override
    public void set(String item) {
        super.set(item.trim());
    }

    @Override
    public String get() {
        return super.get();
    }
}
```

Dòng `extends Store<String>` khiến compiler xem phương thức chuyên biệt của lớp con là override hợp lệ. Tuy nhiên, ở bytecode lớp cha có `set(Object):void` và `get():Object`, còn phương thức con do người dùng viết có `set(String):void` và `get():String`.

Dùng:

```bash
javap -p -s 'ErasureBridgeLab$StringStore'
```

Các descriptor chính được xác nhận:

```text
public void set(java.lang.String);
  descriptor: (Ljava/lang/String;)V

public java.lang.String get();
  descriptor: ()Ljava/lang/String;

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;

public void set(java.lang.Object);
  descriptor: (Ljava/lang/Object;)V
```

Các method `set(String)`, `get():String` là **override cụ thể** đã viết trong source. Hai method `set(Object)`, `get():Object` được `javac` sinh làm bridge để các lời gọi dùng descriptor erased của lớp cha vẫn được chuyển tới override cụ thể.

Bảng đối chiếu:

| Vai trò | Method ở lớp con | JVM descriptor |
| --- | --- | --- |
| Override được viết trong source | `set(String)` | `(Ljava/lang/String;)V` |
| **Bridge** | `set(Object)` | `(Ljava/lang/Object;)V` |
| Override được viết trong source | `get():String` | `()Ljava/lang/String;` |
| **Bridge** | `get():Object` | `()Ljava/lang/Object;` |

Từ góc nhìn source, Java không cho phép bạn tự khai báo hai method chỉ khác kiểu trả về. Dù vậy, ở **class file**, JVM descriptor có chứa kiểu trả về và compiler có thể tạo bridge `get():Object` bên cạnh method `get():String`. Đừng tự viết bridge bằng tay; nó do compiler tạo, và việc viết một phương thức `set(Object)` bên cạnh `set(String)` trong quan hệ generic này thường dẫn đến **name clash**.

## 7. Thí nghiệm C — Xem thân bridge bằng `javap -c`

Chạy:

```bash
javap -p -c 'ErasureBridgeLab$StringStore'
```

Nhìn phần thân cầu nối `set(Object)`. Đoạn opcode đã kiểm chứng:

```text
public void set(java.lang.Object);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #8  // class java/lang/String
     5: invokevirtual #25 // Method set:(Ljava/lang/String;)V
     8: return
```

Đọc theo thứ tự:

1. `aload_0` đẩy tham chiếu `this` lên operand stack.
2. `aload_1` đẩy đối số được truyền vào dưới dạng `Object`.
3. `checkcast String` xác nhận đối số là `String` hoặc `null` (về mặt cast); nếu không tương thích, JVM ném `ClassCastException`.
4. `invokevirtual ... set(String):void` gọi method do lớp con viết.
5. `return` kết thúc bridge.

Mã giả biểu diễn ý tưởng, **không phải đoạn mã nguồn cần thêm vào class**:

```java
// Minh họa compiler-generated bridge, không viết thủ công:
public void set(Object value) {
    set((String) value);
}
```

Chính `checkcast` này giải thích stdout:

```text
raw failure: ClassCastException
```

Raw `Store` gọi `set(123)` với `Integer`; phép cast sang `String` thất bại **trước khi vào phần thân** `set(String)` để trim chuỗi. Với một tham chiếu typed `Store<String>`, compiler từ chối trực tiếp lời gọi `set(123)`, nên sai lầm bị phát hiện sớm hơn.

### Bridge `get():Object` khác gì?

Phần thân từ `javap -c`:

```text
public java.lang.Object get();
  Code:
     0: aload_0
     1: invokevirtual #21 // Method get:()Ljava/lang/String;
     4: areturn
```

Không có đối số cần cast, vì thế cầu nối này chỉ gọi `get():String` rồi trả tham chiếu kết quả dưới dạng `Object`. Một `String` vốn là một `Object`, không cần tạo đối tượng mới.

Chú ý: bản `get():String` mà người dùng viết **gọi** `super.get():Object`; trong bytecode của method thật, compiler chèn **`checkcast String`** khi chuyển kết quả từ lớp cha về `String`. Đừng nhầm `checkcast` nằm trong method thật ấy với phần thân của bridge `get():Object`.

Trong cùng kết quả `javap -c`, phương thức thật có các lệnh điển hình:

```text
public java.lang.String get();
  Code:
     0: aload_0
     1: invokespecial #17 // Method ErasureBridgeLab$Store.get:()Ljava/lang/Object;
     4: checkcast     #8  // class java/lang/String
     7: areturn
```

Sự phân biệt này rất hữu ích khi đọc stack trace hoặc tìm điểm cast sai.

## 8. Thí nghiệm D — Xác nhận bridge qua flags và reflection

Dùng chế độ verbose:

```bash
javap -p -v 'ErasureBridgeLab$StringStore'
```

Ở các method bridge, bạn sẽ thấy một dòng tương tự trích đoạn đã kiểm chứng:

```text
public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC

public void set(java.lang.Object);
  descriptor: (Ljava/lang/Object;)V
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

Các cờ:

- **`ACC_BRIDGE`**: method là cầu nối do compiler sinh phục vụ ngữ nghĩa ghi đè/kiểu.
- **`ACC_SYNTHETIC`**: method do compiler sinh, không phải khai báo thông thường trong mã nguồn của người viết.
- **`ACC_PUBLIC`**: method trong ví dụ có phạm vi public phù hợp với phương thức được ghi đè.

Không phải mọi method synthetic đều là bridge. Muốn khẳng định một method là bridge, cần kiểm tra `ACC_BRIDGE` hoặc API reflection tương ứng.

Phần Java trong `main` xác nhận tương tự:

```java
Method concrete = StringStore.class
        .getDeclaredMethod("set", String.class);
Method bridge = StringStore.class
        .getDeclaredMethod("set", Object.class);
System.out.println(concrete.isBridge()); // false
System.out.println(bridge.isBridge());   // true
System.out.println(bridge.isSynthetic()); // true
```

Đây là trích đoạn từ tệp `ErasureBridgeLab.java`, không phải một chương trình đứng độc lập. `Class.getDeclaredMethod` dùng **kiểu tham số**, nên hai bản `set` có thể được nhận diện riêng. Với bridge `get()` và method `get()` thực cùng danh sách tham số rỗng nhưng khác kiểu trả về trong class file, duyệt `getDeclaredMethods()` rồi lọc `Method.isBridge()` là cách quan sát chắc chắn hơn việc giả định `getDeclaredMethod("get")` chọn một bản nhất định.

Đầu ra đã kiểm chứng của lab:

```text
set(String) bridge: false
set(Object) bridge: true
set(Object) synthetic: true
StringStore bridges: [get, set]
```

Lệnh `sorted()` khiến thứ tự `[get, set]` ổn định, vì Reflection không cam kết thứ tự các method mà `getDeclaredMethods()` trả về.

## 9. Thí nghiệm E — Bound `Number` thay đổi descriptor cầu nối

Bây giờ xem cặp lớp thứ hai:

```java
static class NumberWorker<T extends Number> {
    public T next(T value) {
        return value;
    }
}

static final class IntegerWorker extends NumberWorker<Integer> {
    @Override
    public Integer next(Integer value) {
        return value + 1;
    }
}
```

Ở đây `T` có giới hạn đầu tiên là `Number`, nên type erasure của `T` là **`Number`**, không phải `Object`.

Chạy:

```bash
javap -p -s 'ErasureBridgeLab$NumberWorker'
javap -p -s 'ErasureBridgeLab$IntegerWorker'
```

Kết quả chính từ `NumberWorker`:

```text
public T next(T);
  descriptor: (Ljava/lang/Number;)Ljava/lang/Number;
```

Từ `IntegerWorker`:

```text
public java.lang.Integer next(java.lang.Integer);
  descriptor: (Ljava/lang/Integer;)Ljava/lang/Integer;

public java.lang.Number next(java.lang.Number);
  descriptor: (Ljava/lang/Number;)Ljava/lang/Number;
```

Method `next(Number):Number` là bridge. Chạy:

```bash
javap -p -c 'ErasureBridgeLab$IntegerWorker'
```

Đoạn thân cầu nối đã kiểm chứng:

```text
public java.lang.Number next(java.lang.Number);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #8  // class java/lang/Integer
     5: invokevirtual #17 // Method next:(Ljava/lang/Integer;)Ljava/lang/Integer;
     8: areturn
```

Như vậy, lời gọi qua `NumberWorker<Integer>` vẫn liên kết với chữ ký đã xóa của lớp cha `next(Number):Number`, rồi bridge chuyển tới `next(Integer):Integer` của lớp con. Giá trị đầu vào `7` là `Integer` nên phép cast thành công và method trả `8`.

Quy tắc mở rộng: với một type variable như `<T extends Number & Comparable<T>>`, erasure của `T` dựa vào **bound đầu tiên** là `Number`. Hãy kiểm tra trường hợp cụ thể thay vì mặc định mọi method generic bị xóa về `Object`.

## 10. Thí nghiệm F — Generic method cũng bị erasure

Tệp hoàn chỉnh còn có:

```java
static <T> T echo(T item) {
    return item;
}
```

Đây là một **generic method**, không phải phương thức phụ thuộc tham số kiểu của lớp. Chạy:

```bash
javap -p -s ErasureBridgeLab
```

Dòng liên quan trong kết quả đã kiểm tra:

```text
static <T> T echo(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
```

Vì `T` không có upper bound tường minh, JVM descriptor dùng `Object` ở cả đầu vào và đầu ra. Lời gọi `echo("ok")` vẫn được Java compiler kiểm tra và suy luận kiểu phù hợp, nên stdout:

```text
echo: ok
```

Bằng chứng này tránh một nhầm lẫn phổ biến: type erasure không chỉ xảy ra trên generic class như `Store<T>`; nó còn áp dụng cho type parameter khai báo ở method `<T> T echo(T)`.

**Phân biệt:** `echo` không tự sinh bridge chỉ vì nó là generic. Bridge trong lab xuất hiện do quan hệ **ghi đè** có descriptor đặc biệt cần duy trì sau erasure.

## 11. Sơ đồ đường đi của lời gọi `set`

Khi viết:

```java
Store<String> store = new StringStore();
store.set("  java  ");
```

Mô hình luồng thực thi phù hợp với bytecode đã quan sát:

```text
Java source: Store<String>.set("  java  ")
                |
                v
Compiler kiểm tra argument là String
                |
                v
JVM call theo descriptor Store.set(Object):void
                |
                v
Đối tượng thực: StringStore
                |
                v
StringStore.set(Object):void     [BRIDGE]
                |
       checkcast String
                |
                v
StringStore.set(String):void     [SOURCE OVERRIDE]
                |
       String.trim()
                |
                v
Store.set(Object):void          [SUPER IMPLEMENTATION]
                |
                v
Field item lưu đối tượng String "java"
```

Đây là sơ đồ hướng dẫn đọc bytecode, không phải cú pháp Java để chạy. Với compiler và kiểu dispatch khác nhau, opcode có thể thay đổi, nhưng bằng chứng của lab gồm hai đường chính: method bridge nhận descriptor erased và method override chuyên biệt xử lý giá trị.

Khi gọi `store.get()`, JVM tương tự dùng descriptor `Store.get():Object`, chọn bridge `StringStore.get():Object`, bridge gọi `StringStore.get():String`, phương thức thật gọi `super.get():Object` và cast kết quả về `String`. Nhờ bridge, tính đa hình ở source không bị phá hỏng bởi erasure.

## 12. Giải thích hiện tượng raw type trong cùng lab

Chủ ý cuối `main`:

```java
Store raw = new StringStore();
try {
    raw.set(123);
} catch (ClassCastException ex) {
    System.out.println("raw failure: "
            + ex.getClass().getSimpleName());
}
```

`Store` ở đây là **raw type** vì bỏ đối số kiểu `<T>`. Trong Java source, lời gọi `raw.set(123)` được cho phép với cảnh báo unchecked vì chữ ký erased của `set` nhận `Object`. Tuy nhiên đối tượng thật vẫn là `StringStore`; cầu nối `set(Object)` của lớp này yêu cầu cast sang `String`. `Integer` không phù hợp, nên runtime ném `ClassCastException`.

Hai điểm cần rút ra:

- **Generic type safety** được compiler áp dụng trong lời gọi typed thông thường. Raw type cố tình đi qua một ranh giới ít kiểm tra hơn và làm lộ nguy cơ.
- **Bridge không phải công cụ chuyển kiểu tùy ý.** Nó chỉ bảo tồn hợp đồng ghi đè; phép `checkcast` vẫn có thể thất bại với dữ liệu vi phạm giả định.

Không kết luận rằng “mọi raw method đều ném exception”: nếu đối số thật là `String`, bridge có thể cast thành công. Lỗi phụ thuộc kiểu dữ liệu thực truyền vào và bytecode của phương thức đích.

## 13. Bộ lệnh kiểm tra nhanh và cách tự đối chiếu

Một trình tự tái lập từ đầu đến cuối:

```bash
# Bước 1: Biên dịch cùng cảnh báo cần quan sát.
javac -Xlint:rawtypes -Xlint:unchecked ErasureBridgeLab.java

# Bước 2: Quan sát output.
java ErasureBridgeLab

# Bước 3: Quan sát erasure ở lớp generic.
javap -p -s 'ErasureBridgeLab$Store'

# Bước 4: Đếm method thật và bridge ở lớp con.
javap -p -s 'ErasureBridgeLab$StringStore'

# Bước 5: Quan sát cast và lệnh gọi trong bridge.
javap -p -c 'ErasureBridgeLab$StringStore'

# Bước 6: Xác minh flags bridge/synthetic.
javap -p -v 'ErasureBridgeLab$StringStore'

# Bước 7: Đối chiếu upper bound Number.
javap -p -s 'ErasureBridgeLab$NumberWorker'
javap -p -s 'ErasureBridgeLab$IntegerWorker'

# Bước 8: Đối chiếu generic method.
javap -p -s ErasureBridgeLab
```

Các dòng bắt đầu bằng `#` là chú thích shell trong Bash; trong PowerShell cũng có thể sử dụng `#` cho chú thích. Nếu Windows `cmd.exe` được sử dụng, hãy chạy các lệnh `javac`/`java`/`javap` riêng, không sao chép các dòng chú thích vào `cmd`.

Các mệnh đề để kiểm tra từ output:

| Mệnh đề | Bằng chứng cần thấy | Kỳ vọng |
| --- | --- | --- |
| Erasure của `Store<T>` là `Object` | Descriptor của field/set/get | `Object` |
| `StringStore` có bridge nhận `Object` | `javap -s` | `set(Object):void` |
| `StringStore` có bridge trả `Object` | `javap -s` | `get():Object` |
| Bridge thực hiện cast khi nhận tham số | `javap -c` | `checkcast String` |
| Bridge là compiler-generated | `javap -v` | `ACC_BRIDGE, ACC_SYNTHETIC` |
| Reflection nhận diện bridge | `Method.isBridge()` | `true` với `set(Object)` |
| Erasure của `T extends Number` | `NumberWorker.next` | `Number` |
| Bridge lớp con giới hạn Number | `IntegerWorker.next` | `next(Number):Number` |
| Generic method `echo(T)` bị erasure | Descriptor của `echo` | `(Object)Object` |
| Raw type phá an toàn kiểu | `raw.set(123)` | `ClassCastException` |

Để kết luận một mục **PASS**, hãy chỉ ra dòng descriptor/flag/bytecode tương ứng, thay vì chỉ dựa vào chữ ký generic mà `javap` in ở dòng trên.

## 14. Những lỗi thường gặp khi thực hành

### Không tìm thấy `ErasureBridgeLab$StringStore`

Nguyên nhân thường gặp là chạy `javap` ở thư mục sai, chưa biên dịch, hoặc shell xử lý ký tự `$`. Kiểm tra class file đã sinh, đặt tên lớp lồng trong dấu nháy đơn, hoặc truyền `-classpath` trỏ đến thư mục output của `javac`.

### Chỉ dùng `javap ErasureBridgeLab` và không thấy method bridge

Bridge được sinh trong **lớp con** `StringStore` và `IntegerWorker`, không nằm ở class `ErasureBridgeLab` bao quanh. Cần hướng `javap` vào chính class con.

### Tưởng `T` hiển thị trong output `javap` nghĩa là chưa bị xóa

`javap` có thể đọc generic `Signature`. Hãy kiểm tra **`descriptor:`** để xác định kiểu JVM dùng. Ví dụ `T get()` có descriptor `()Ljava/lang/Object;`.

### Kết luận `get():Object` là một overload thông thường do tác giả viết

Bridge được đánh dấu `ACC_BRIDGE` và `ACC_SYNTHETIC`, không xuất hiện trong source. JVM descriptor chứa cả kiểu trả về nên compiler có thể đặt bridge `get():Object` bên cạnh `get():String`.

### Cho rằng mọi bridge phải có `checkcast`

Bridge `set(Object)` có cast đầu vào; bridge `get():Object` trong ví dụ chỉ ủy quyền tới `get():String`. Có thể có cast ở **phương thức thật** hoặc **điểm gọi** chứ không nhất thiết ở mọi cầu nối.

### Nhầm `StringStore.get():String` với `StringStore.get():Object`

Cả hai hiện diện trong class file và khác **return descriptor**. Hãy đọc phương thức đang xem ở đầu khối `javap -c` trước khi diễn giải opcode.

### Nghĩ raw type tự động chuyển `Integer` thành `String`

Raw type bỏ bớt kiểm tra lúc biên dịch; bridge kiểm tra cast tại runtime. Khi kiểu không tương thích, chương trình ném `ClassCastException` chứ không tự chuyển giá trị.

### Dùng kết quả `getDeclaredMethods()` theo thứ tự cố định

Reflection không bảo đảm thứ tự danh sách method. Khi cần so khớp output, hãy lọc `isBridge`, chuẩn hóa tên/chữ ký và sắp xếp có chủ đích như chương trình mẫu.

### Thấy `Number` rồi suy luận là sai vì tài liệu nói “generic về Object”

Erasure thay type variable bằng **upper bound hiệu dụng**. Với `T extends Number`, descriptor dùng `Number`; `Object` là trường hợp không có bound (hoặc upper bound hiệu dụng là `Object`).

### Sao chép đoạn mã giả bridge vào source

Compiler tự tạo cầu nối. Nếu tự viết method có cùng erasure với phương thức inherited, bạn có thể tạo name clash. Chỉ triển khai override typed và để compiler xử lý bridge.

## 15. Bài tập biến đổi chương trình và dự đoán kết quả

**Bài 1 — Bỏ `@Override` ở `StringStore.set(String)`.** Dự đoán bridge có biến mất không nếu chữ ký và quan hệ kế thừa vẫn giống cũ. Sau đó biên dịch và quan sát lại `javap`.

*Đáp án định hướng:* `@Override` là bước kiểm tra của compiler đối với ý định ghi đè. Việc bỏ annotation không làm đổi quan hệ override hợp lệ; các cầu nối cần thiết thường vẫn được sinh. Tuy nhiên, giữ annotation để phát hiện sớm sai sót về chữ ký.

**Bài 2 — Đổi giới hạn `NumberWorker<T extends Number>` thành `NumberWorker<T>`.** Cần sửa điều gì để `IntegerWorker` vẫn hợp lệ? Dự đoán descriptor của `next(T)` ở lớp cha và bridge trong lớp con.

*Đáp án định hướng:* `T` mới xóa về `Object`; nếu các phần phương thức vẫn hợp lệ, descriptor cha là `(Object)Object`, và cầu nối lớp con cần `next(Object):Object`. Chạy `javap -s` sau khi sửa để xác minh.

**Bài 3 — Đổi `StringStore.get()` thành trả chuỗi cố định.** Hỏi bridge `get():Object` có còn cần không?

*Đáp án định hướng:* nếu vẫn ghi đè `Store<String>.get()` với kiểu trả `String`, quan hệ bytecode với phương thức cha trả `Object` vẫn tồn tại. Việc thay thân phương thức không tự xóa nhu cầu bridge.

**Bài 4 — Lấy danh sách mọi bridge của `IntegerWorker` bằng reflection.** Viết một đoạn tương tự `Arrays.stream(...).filter(Method::isBridge)` và so sánh với `StringStore`.

*Đáp án định hướng:* `IntegerWorker` có một bridge `next(Number):Number` trong ví dụ hiện tại, trong khi `StringStore` có bridge `get` và `set`. Đếm method trên đúng class, không gộp cả method thừa kế vào kết quả `getDeclaredMethods()`.

**Bài 5 — Phân loại cast.** Trong `javap -c`, tìm `checkcast` trong `StringStore.get():String` và trong `StringStore.set(Object):void`. Cái nào nằm trong bridge?

*Đáp án định hướng:* `set(Object)` là bridge, cast đầu vào từ `Object` thành `String`. `get():String` là method thật, cast kết quả nhận từ `Store.get():Object` để trả `String`.

**Bài 6 — Kiểm tra sai kiểu qua raw.** Thay `raw.set(123)` bằng `raw.set("correct")`, biên dịch và chạy. Cảnh báo và exception thay đổi thế nào?

*Đáp án định hướng:* cảnh báo raw/unchecked vẫn còn vì kiểu tham chiếu raw; nhưng giá trị thực là `String` nên cast của bridge thành công, không còn `ClassCastException` tại lời gọi ấy.

**Bài 7 — Nhìn method generic `echo`.** Vì sao `echo("ok")` không tạo bridge dù descriptor là `(Object)Object`?

*Đáp án định hướng:* generic erasure tự nó không buộc compiler tạo bridge. Bridge phục vụ những quan hệ override/descriptor cần kết nối; `echo(T)` ở đây là phương thức static generic độc lập, không ghi đè method generic ở lớp cha.

## 16. Tự đánh giá bài thực hành

Bạn đã hoàn thành bài khi có thể:

- Biên dịch `ErasureBridgeLab.java` bằng `javac`, giải thích cảnh báo raw/unchecked và đối chiếu stdout chính xác.
- Chỉ ra `Object` trong descriptor `Store<T>`, trong khi `javap` vẫn hiển thị ký hiệu generic `T`.
- Chứng minh `StringStore` chứa hai bridge bằng **descriptor, bytecode và flags**, không chỉ dựa vào `@Override`.
- Phân biệt `checkcast` ở bridge `set(Object)` với cast trong method thật `get():String`.
- Giải thích vì sao `IntegerWorker` có bridge với `Number` thay vì `Object`.
- Đọc được `ACC_BRIDGE`, `ACC_SYNTHETIC`, `Signature` và giải thích vai trò khác nhau của chúng.
- Kết nối bằng chứng runtime `isBridge()`, lỗi raw type và cơ chế dispatch qua lớp cha.

**Kết quả cốt lõi:** type erasure biến những vị trí dùng `T` thành kiểu upper bound phù hợp trong JVM descriptor; bridge method được `javac` sinh để giữ đúng quan hệ ghi đè và đa hình khi descriptor của override chuyên biệt khác dạng erased. `javap -s`, `-c`, `-v` cùng reflection cho phép tự chứng minh cả **hình dạng bytecode** lẫn **hành vi chạy** của cơ chế đó.
