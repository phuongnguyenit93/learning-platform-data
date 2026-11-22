# Phương thức cầu nối (bridge method) bảo toàn đa hình trong Java Generics

## 1. Vấn đề: sau xóa kiểu, JVM vẫn phải gọi đúng phương thức ghi đè

Trong Java, **đa hình** có nghĩa là khi gọi một phương thức có thể ghi đè qua tham chiếu lớp cha hoặc interface, việc thực thi phải chọn phần cài đặt phù hợp với lớp thực tế của đối tượng.

~~~java
Box<String> box = new StringBox();
box.set("java");
String result = box.get();
~~~

Với một lớp cơ sở generic `Box<T>` và lớp con `StringBox extends Box<String>`, lập trình viên mong đợi `set` và `get` ghi đè ở `StringBox` hoạt động khi gọi qua `Box<String>`.

Nhưng **type erasure (xóa kiểu)** tạo ra khác biệt giữa chữ ký kiểu ở source Java và descriptor mà JVM sử dụng:

- Ở `Box<T>`, tham số `T` không có giới hạn tường minh nên bị xóa thành **Object**.
- Ở `StringBox`, phương thức chuyên biệt có tham số hoặc kiểu trả về **String**.
- JVM phân giải phương thức dựa trên tên và descriptor; chữ ký `set(Object)` khác `set(String)`, còn `get():Object` khác `get():String` ở mức descriptor.

Để bảo toàn quy tắc ghi đè đã được compiler xác định từ source Java, **javac có thể tự sinh phương thức cầu nối (bridge method)**. Đây là một phương thức có bytecode thật, chuyển lời gọi từ chữ ký sau erasure sang phần cài đặt chuyên biệt.

Với `set`, bridge cần ép kiểu đối số Object về String rồi chuyển tiếp đến `set(String)`. Với `get`, bridge có thể chỉ cần gọi `get():String` và trả kết quả ở dạng Object.

Bridge method là một chi tiết do compiler tạo để bảo toàn **tính đa hình và tương thích nhị phân**, không phải phương thức người lập trình bắt buộc phải viết thủ công.

## 2. Hình dung trường hợp điển hình

Giả sử hai lớp:

~~~java
class Box<T> {
    private T value;

    public void set(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}

class StringBox extends Box<String> {
    @Override
    public void set(String value) {
        super.set(value.toUpperCase());
    }

    @Override
    public String get() {
        return super.get();
    }
}
~~~

Ở **source Java**, `set(String)` và `get():String` của `StringBox` ghi đè hợp lệ hai phương thức generic của `Box<String>`.

Sau xóa kiểu, các phương thức cơ sở về mặt descriptor tương ứng:

~~~text
Box.set(java.lang.Object): void
Box.get(): java.lang.Object
~~~

Còn các phương thức khai báo trực tiếp trong `StringBox` tương ứng:

~~~text
StringBox.set(java.lang.String): void
StringBox.get(): java.lang.String
~~~

Không có các bridge, lời gọi dùng descriptor `set(Object)` từ lớp cơ sở có thể bỏ qua chuyên biệt hóa `set(String)` ở lớp con. Javac vì vậy sinh thêm các điểm vào có descriptor tương thích với bản đã xóa của lớp cha.

Có thể hình dung `StringBox` **gần tương đương** với các phương thức bổ sung sau:

~~~java
// PSEUDOCODE: không được chép trực tiếp vào StringBox,
// vì chữ ký và ràng buộc nguồn Java có thể gây name clash.
public void set(Object value) {
    set((String) value);
}

public Object get() {
    return get(); // Chuyển đến get() trả String theo descriptor riêng.
}
~~~

Hai phương thức trên là **mã minh họa bytecode ở dạng Java giả lập**, không phải source hợp lệ cần viết thêm. Trong bytecode, JVM phân biệt các descriptor khác nhau; ở Java source, overload không thể chỉ khác kiểu trả về và cố viết `set(Object)` có thể xung đột erasure.

**Điểm mấu chốt:** `@Override` và kiểm tra kiểu generic diễn ra trên chương trình Java ban đầu. Compiler chịu trách nhiệm tạo cầu nối cần thiết để quan hệ ghi đè ấy vẫn đúng sau khi loại bỏ phần lớn thông tin type parameter.

## 3. Chương trình Java 17+ hoàn chỉnh

Lưu nội dung sau trong tệp **BridgeMethodDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class BridgeMethodDemo {
    static class Box<T> {
        private T value;

        public void set(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }
    }

    static final class StringBox extends Box<String> {
        @Override
        public void set(String value) {
            super.set(value.toUpperCase());
        }

        @Override
        public String get() {
            return super.get();
        }
    }

    public static void main(String[] args) {
        // Lời gọi qua kiểu cha generic phải chọn override của StringBox.
        Box<String> box = new StringBox();
        box.set("java");
        System.out.println("value=" + box.get());

        // Reflection phát hiện các phương thức cầu nối compiler tạo.
        System.out.println(
                "bridge names=" +
                Arrays.stream(StringBox.class.getDeclaredMethods())
                        .filter(Method::isBridge)
                        .map(Method::getName)
                        .sorted()
                        .toList()
        );

        // Raw type bỏ kiểm tra generic ở phía gọi và có cảnh báo.
        Box raw = box;
        try {
            raw.set(123);
        } catch (ClassCastException ex) {
            System.out.println("raw call=ClassCastException");
        }

        System.out.println("value after=" + box.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -Xlint:unchecked BridgeMethodDemo.java
java BridgeMethodDemo
~~~

Do gọi `raw.set(123)` trên raw `Box`, trình biên dịch sẽ đưa ra **unchecked warning**. Cảnh báo nằm ở đầu ra biên dịch, không phải stdout của chương trình.

Stdout khi chạy:

~~~text
value=JAVA
bridge names=[get, set]
raw call=ClassCastException
value after=JAVA
~~~

Giải thích:

1. `box` có kiểu tĩnh `Box<String>` nhưng chứa đối tượng `StringBox`. Gọi `box.set("java")` phải thực hiện override tại `StringBox`, đổi dữ liệu thành chữ hoa. Kết quả `box.get()` là `JAVA`.
2. `StringBox.class.getDeclaredMethods()` bao gồm các phương thức do compiler tạo ngay trên `StringBox`. `Method.isBridge()` nhận diện bridge methods. Ví dụ này có bridge cho cả `set` và `get`; danh sách được sắp xếp để thứ tự in ổn định.
3. Tham chiếu raw `Box` cho phép gọi `set(123)` ở compile time kèm cảnh báo. Tại runtime, lời gọi `set(Object)` được phân phối tới bridge của `StringBox`, nơi compiler chèn **checkcast String** trước khi chuyển tiếp đến `set(String)`.
4. Đối số là Integer, không phù hợp String nên bridge ném `ClassCastException`. Giá trị cũ trong Box không bị thay đổi; lời gọi cuối cùng vẫn in `JAVA`.

**Lưu ý:** Raw type ở đây chỉ để quan sát kiểm tra runtime bên trong bridge. API thực tế nên giữ `Box<String>`; câu lệnh `box.set(123)` bình thường sẽ bị javac từ chối ngay tại compile time.

## 4. Kiểm tra bridge method trong bytecode bằng javap

Sau khi biên dịch, chạy:

~~~bash
javap -c -p 'BridgeMethodDemo$StringBox'
~~~

Tùy shell, cần quote tên nested class để ký tự `$` không bị diễn giải; trên Windows CMD có thể dùng dấu nháy kép. Có thể xem thêm cờ synthetic và bridge ở class file:

~~~bash
javap -v -p 'BridgeMethodDemo$StringBox'
~~~

Bạn sẽ thấy **cả các phương thức String chuyên biệt lẫn các phương thức do compiler tạo**. Dạng mô tả bytecode quan trọng với `set`:

~~~text
public void set(java.lang.Object);
  ... aload_0
  ... aload_1
  ... checkcast java/lang/String
  ... invokevirtual set:(Ljava/lang/String;)V
  ... return
~~~

Bridge của `get` có dạng khái niệm:

~~~text
public java.lang.Object get();
  ... aload_0
  ... invokevirtual get:()Ljava/lang/String;
  ... areturn
~~~

Offset, số constant-pool và một vài chi tiết opcode có thể khác nhau giữa các bản javac. Điều cần kiểm tra là **descriptor tương thích với lớp cơ sở, cờ bridge/synthetic và lời gọi chuyển tiếp tới phương thức chuyên biệt**.

Nếu dùng `javap -v`, bridge do javac tạo thường có cờ **ACC_BRIDGE** và **ACC_SYNTHETIC**. Reflection có các hàm tương ứng:

~~~java
method.isBridge();
method.isSynthetic();
~~~

Trong Java, hai thuộc tính có ý nghĩa khác nhau: `isBridge` cho biết method là cầu nối, còn `isSynthetic` chỉ method không khai báo trực tiếp trong mã nguồn; không phải mọi synthetic method đều là bridge.

### JVM descriptor cần hiểu đúng

Với `Box<T>` không có bound tường minh:

| Phương thức | Descriptor ở JVM |
| --- | --- |
| `Box.set(T)` sau erasure | `(Ljava/lang/Object;)V` |
| `StringBox.set(String)` | `(Ljava/lang/String;)V` |
| Bridge `StringBox.set(Object)` | `(Ljava/lang/Object;)V` |
| `Box.get()` sau erasure | `()Ljava/lang/Object;` |
| `StringBox.get():String` | `()Ljava/lang/String;` |
| Bridge `StringBox.get():Object` | `()Ljava/lang/Object;` |

Ký tự `V` đại diện cho void, còn `Ljava/lang/String;` đại diện cho reference type java.lang.String. JVM có thể phân biệt các method descriptor bao gồm cả kiểu trả về; Java source không cho overload chỉ dựa trên kiểu trả về.

## 5. Phương thức cầu nối cho generic interface

Bridge method không chỉ xuất hiện khi một lớp extends lớp cha generic. Interface generic cũng có vấn đề tương tự:

~~~java
interface Converter<T> {
    T convert(T input);
}

final class TrimConverter implements Converter<String> {
    @Override
    public String convert(String input) {
        return input.trim();
    }
}
~~~

Ở source, `convert(String)` ghi đè hợp lệ `convert(T)` sau khi `T` được thay bằng String.

Sau erasure, method trong interface có descriptor gần như:

~~~text
Converter.convert(Object) -> Object
~~~

Trong `TrimConverter`, phương thức chuyên biệt:

~~~text
TrimConverter.convert(String) -> String
~~~

Javac thêm bridge tương thích `convert(Object) -> Object`. Bridge kiểm tra Object thành String trước khi gọi phương thức chuyên biệt và trả kết quả như Object.

Ví dụ áp dụng:

~~~java
Converter<String> converter = new TrimConverter();
String result = converter.convert("  Java  "); // "Java"
~~~

Nếu thiếu cầu nối, cơ chế gọi qua interface generic sau erasure có thể không tìm đúng phần cài đặt chuyên biệt. Cấu trúc bridge giúp lời gọi interface vẫn hoạt động như hợp đồng override trong Java source.

**Đây là đoạn minh họa để ghép vào chương trình có chứa các định nghĩa cùng đoạn**, không phải một tệp Java độc lập vì chưa có hàm main hoặc public class.

## 6. Phương thức có bound: erasure không phải lúc nào cũng thành Object

Cận kiểu có thể làm kiểu sau erasure khác Object.

~~~java
class NumberHolder<T extends Number> {
    public void accept(T input) {
        System.out.println(input.intValue());
    }
}

final class IntegerHolder extends NumberHolder<Integer> {
    @Override
    public void accept(Integer input) {
        System.out.println(input + 1);
    }
}
~~~

Trong `NumberHolder`, erasure của T là **Number** vì `T extends Number`. Vì thế descriptor của phương thức cơ sở nhận Number, còn override nhận Integer:

~~~text
NumberHolder.accept(Number)
IntegerHolder.accept(Integer)
bridge IntegerHolder.accept(Number) → cast Integer → accept(Integer)
~~~

Bridge **không bắt buộc dùng Object**. Nó phải khớp chữ ký ở phía lớp cơ sở/interface sau erasure. Quy tắc erasure của type variable lấy cận trái nhất, nên nếu có giới hạn class/interface phức tạp hơn, cách phát sinh cầu nối cũng dựa trên chữ ký runtime thực tế.

Nếu dùng raw NumberHolder và truyền một đối tượng Number không phải Integer tới một IntegerHolder, bridge có thể ném ClassCastException khi checkcast Integer. API có kiểu `NumberHolder<Integer>` bình thường sẽ từ chối đối số không phù hợp ngay khi biên dịch.

## 7. Bridge cũng xuất hiện khi trả về kiểu hiệp biến

**Covariant return type** cho phép override trả về subtype của kiểu trả về gốc:

~~~java
class Animal {
    Animal copy() {
        return new Animal();
    }
}

final class Dog extends Animal {
    @Override
    Dog copy() {
        return new Dog();
    }
}
~~~

Ngay cả khi **không có generics**, kiểu trả về của `Animal.copy()` và `Dog.copy()` khác nhau ở JVM descriptor. Compiler có thể sinh cầu nối với descriptor trả Animal trong Dog để duy trì dispatch đúng qua tham chiếu Animal.

Từ đó, quy tắc “bridge method luôn do generics tạo ra” là không đúng. Có ít nhất hai tình huống thường gặp: **xóa kiểu làm thay đổi chữ ký ghi đè** và **override có kiểu trả về hiệp biến**.

Ví dụ:

~~~java
Animal animal = new Dog();
Animal duplicate = animal.copy();
System.out.println(duplicate instanceof Dog); // true
~~~

Đa hình được giữ: phương thức thực hiện thuộc Dog và trả về Dog, mặc dù biến ngoài có kiểu Animal.

## 8. Cách bridge bảo toàn đa hình, từng bước

Với ví dụ Box/StringBox, khi gọi:

~~~java
Box<String> box = new StringBox();
box.set("java");
~~~

một cách hình dung logic của quá trình là:

1. Javac kiểm tra `StringBox.set(String)` ghi đè `Box<String>.set(String)` hợp lệ ở mức source.
2. Sau erasure, lời gọi qua `Box` mang descriptor `set(Object)`.
3. StringBox có bridge `set(Object)`, cùng descriptor cần thiết để override ở bytecode.
4. Dispatch động chọn bridge tại đối tượng runtime StringBox.
5. Bridge ép đối số thành String, rồi gọi `StringBox.set(String)`.
6. Phương thức chuyên biệt thực hiện chuyển chữ hoa; kết quả nhận được tuân thủ ý nghĩa đa hình của source.

Tương tự với get:

~~~java
String value = box.get();
~~~

Lời gọi qua `Box` có descriptor trả Object sau erasure; JVM có thể dispatch vào bridge get():Object trong StringBox, bridge gọi get():String thực sự, rồi caller sử dụng kết quả như String. Javac có thể chèn **checkcast String tại caller** vì caller nhận Object từ lời gọi đã xóa kiểu.

Vì thế có thể gặp **hai kiểu kiểm tra khác vị trí** trong cùng ví dụ:

- Cast trong bridge **set(Object)** kiểm tra đối số trước khi chuyển sang set(String).
- Cast tại phía caller **get()** kiểm tra kết quả trả Object trước khi dùng như String.

Chúng phục vụ những thao tác khác nhau. Bridge method là **một phương thức sinh ra**, còn checkcast là **một opcode**; không nên coi chúng là cùng một khái niệm.

## 9. Vì sao không nên tự viết một bridge method?

Cố tự viết phương thức `set(Object)` cạnh `set(String)` trong lớp con generic có thể gặp **name clash** vì erasure hoặc làm thay đổi hợp đồng overload/override, tùy chữ ký cụ thể.

Ví dụ **cố ý không biên dịch**:

~~~java
class Base<T> {
    void set(T value) {}
}

class BadChild extends Base<String> {
    void set(Object value) {} // Name clash với phương thức được kế thừa.
}
~~~

Vì `set(T)` bị xóa thành `set(Object)`, khai báo ở lớp con không thể dùng tùy ý để “thay bridge” trong source Java. Nếu lớp con muốn ghi đè đúng phương thức đã được chuyên biệt hóa, hãy viết:

~~~java
class GoodChild extends Base<String> {
    @Override
    void set(String value) {}
}
~~~

Sau đó để compiler phát sinh bridge khi cần. Với phương thức generic đúng chuẩn, `@Override` là công cụ quan trọng: nó yêu cầu compiler xác minh rằng chữ ký thực sự ghi đè một phương thức đã tồn tại.

## 10. Phân biệt bridge, overload, override và method hiding

| Cơ chế | Ý nghĩa | Khi nào dispatch tới phần cài đặt lớp con? |
| --- | --- | --- |
| **Override** | Lớp con thay thế implementation của một instance method được kế thừa theo quy tắc Java. | Gọi instance method qua lớp cha/interface vẫn chọn override theo runtime object. |
| **Overload** | Cùng tên phương thức nhưng khác danh sách tham số ở source. | Chọn overload chủ yếu tại compile time theo kiểu biểu thức và tham số. |
| **Bridge method** | Compiler sinh thêm phương thức với descriptor phù hợp, chuyển tiếp đến implementation chuyên biệt. | Hỗ trợ override vẫn hoạt động khi erasure/covariant return làm descriptor khác nhau. |
| **Method hiding** | Phương thức static trong subclass che phương thức static cùng chữ ký của parent. | Static method không tham gia dynamic dispatch như instance override; bridge không làm static hiding thành override. |

Ví dụ overload:

~~~java
class Printer {
    void print(Object value) {
        System.out.println("Object");
    }
    void print(String value) {
        System.out.println("String");
    }
}
~~~

Lựa chọn giữa `print(Object)` và `print(String)` dựa vào kiểu tĩnh của đối số khi biên dịch. Điều này khác với vấn đề bridge: bridge giúp **một override đã được xác định** tiếp tục tham gia dynamic dispatch đúng sau erasure.

## 11. Kiểm tra bridge bằng Reflection

JDK cung cấp:

~~~java
Method.isBridge()
Method.isSynthetic()
Method.getParameterTypes()
Method.getReturnType()
Method.getDeclaredMethods()
~~~

Ví dụ kiểm tra có phân biệt:

~~~java
for (Method method : StringBox.class.getDeclaredMethods()) {
    if (method.isBridge()) {
        System.out.println(method.getName() + ": " + method.isSynthetic());
    }
}
~~~

Mảnh code trên giả định StringBox đã được khai báo cùng scope. Thứ tự từ `getDeclaredMethods()` **không được API bảo đảm**, nên nếu muốn có output lặp lại ổn định thì cần `sorted()` theo tên hoặc descriptor.

Một phương thức bridge do javac sinh thông thường cũng synthetic, nhưng bạn nên dùng `isBridge()` để xác định đúng bridge thay vì suy luận từ `isSynthetic()` một mình. Reflection có thể nhìn thấy những method compiler-generated mà source code không có khai báo tường minh, điều này bình thường.

### Khi reflection tạo nhiều phương thức “trùng tên”

Công cụ quét API có thể thấy nhiều `get()`, `set(...)` hoặc `convert(...)` mà tên có vẻ trùng nhau. Đừng vội kết luận class định nghĩa API thừa. Hãy kiểm tra:

- `isBridge()` và `isSynthetic()`.
- Danh sách tham số từ `getParameterTypes()`.
- Kiểu trả về từ `getReturnType()`.
- Quan hệ lớp cha/interface generic và những override chuyên biệt.

Khi tạo tài liệu API, nhiều công cụ chọn loại bỏ hoặc ẩn bridge method khỏi danh sách API dành cho người lập trình, nhưng vẫn giữ chúng trong bytecode để đảm bảo hành vi thực thi.

## 12. Những lỗi và ngộ nhận thường gặp

### Nhầm “erasure phá đa hình”

Type erasure có thể thay đổi chữ ký ở bytecode, nhưng javac hỗ trợ bridge để giữ hợp đồng overriding hợp lệ đã xác định ở source. Một lời gọi qua kiểu cha sẽ vẫn chọn phần cài đặt lớp con như mong đợi.

### Nhầm “StringBox được phép nhận Integer vì set sau erasure nhận Object”

Chữ ký source của `Box<String>.set` nhận String. Nếu dùng reference được tham số hóa đúng, compiler chặn Integer. Đối số không đúng kiểu chỉ có thể lọt qua đường raw/unchecked hay lối truy cập không an toàn khác; bridge có thể phát hiện lỗi runtime.

### Nhầm “bridge = cast”

Bridge là method có thể chứa checkcast, invoke và return. Còn checkcast là chỉ thị kiểm tra tham chiếu. Bridge trả về Object từ get():String thường không cần cast String ngay bên trong bridge; cast của caller là chuyện khác.

### Nhầm “mọi phương thức generic đều sinh bridge”

Generic class không tự động cần bridge chỉ vì có T. Bridge xuất hiện khi phải bắc cầu chữ ký/descriptor để quan hệ override hoạt động đúng. Nếu lớp con không chuyên biệt hóa override hoặc descriptor vẫn tương thích, có thể không có bridge.

### Nhầm “bridge luôn trả Object”

Descriptor phải phù hợp với phương thức ở phía lớp cha/interface sau erasure. Nếu type variable có bound, descriptor có thể sử dụng Number, Serializable hoặc một class/interface tương ứng. Trường hợp covariant return không generic cũng có thể trả một lớp cha khác Object.

### Nhầm “tên và số lượng bridge là hợp đồng public API”

Hình dạng bridge phụ thuộc các phương thức ghi đè, hierarchy, compiler và target bytecode. Không nên viết logic nghiệp vụ dựa trên số bridge hoặc offset bytecode của một bản javac cụ thể. Kiểm tra những thuộc tính đó chỉ phù hợp cho học tập, phân tích và công cụ chuyên biệt.

## 13. Khi nào cần quan tâm bridge method trong công việc thực tế?

**Khi debug ClassCastException:** nếu stack trace dính đến một method synthetic/bridge hoặc một lời gọi raw generic, xem tham số runtime có phù hợp subtype mà lớp con thực sự chấp nhận hay không. Một lời gọi raw `set(Object)` có thể bị bridge ép thành String và thất bại.

**Khi dùng reflection hoặc tạo framework:** bridge có thể xuất hiện thêm trong `getDeclaredMethods()`. Nếu quét annotation, xây routing hoặc đăng ký handler, cần xác định method thực sự do người dùng viết và phương thức bridge chuyển tiếp, tránh xử lý nhầm một phương thức hai lần. Quy tắc mapping annotation/bridge còn phụ thuộc framework đang dùng.

**Khi phân tích bytecode:** so sánh `javap -c -p` của superclass generic và subclass chuyên biệt, xác định descriptor, ACC_BRIDGE/ACC_SYNTHETIC, checkcast và lệnh invoke chuyển tiếp.

**Khi thiết kế class generic:** viết override đúng kiểu và thêm `@Override`. Không can thiệp vào bridge do compiler tạo và không phụ thuộc giả định erasure khiến JVM tự đoán kiểu generic ở runtime.

**Khi đánh giá binary compatibility:** bridge là một trong các cơ chế giúp class file và lời gọi biên dịch với descriptor đã xóa tương thích. Tuy nhiên, thay đổi API public, generic bounds hoặc quan hệ kế thừa vẫn có thể tạo lỗi tương thích; bridge không bảo đảm mọi kiểu thay đổi thư viện đều an toàn.

## 14. Câu hỏi tự kiểm tra

**1.** Vì sao `StringBox.set(String)` cần bridge tương thích `set(Object)`?

**Đáp án:** Sau erasure, chữ ký phương thức `Box.set(T)` là `set(Object)`. Bridge có descriptor ấy để dynamic dispatch qua Box vẫn đi tới override set(String).

**2.** Khi tham chiếu raw Box gọi `set(123)` trên StringBox, tại sao có thể ném ClassCastException trước khi vào set(String)?

**Đáp án:** Bridge set(Object) kiểm tra đối số bằng checkcast String rồi mới chuyển tiếp. Integer không tương thích String nên phép kiểm tra thất bại.

**3.** Bridge get():Object có bắt buộc ép kiểu String ở trong bridge không?

**Đáp án:** Không. Nó có thể gọi get():String và trả tham chiếu đó như Object. Caller dùng kết quả đã xóa kiểu như String có thể thực hiện checkcast String riêng.

**4.** `method.isSynthetic()` có đủ để kết luận method là bridge không?

**Đáp án:** Không. Synthetic bao gồm các thành viên do compiler tạo vì nhiều lý do; cần kiểm tra `isBridge()` để nhận diện bridge.

**5.** Bridge method có tồn tại khi không sử dụng generics không?

**Đáp án:** Có thể có khi ghi đè dùng kiểu trả về hiệp biến, chẳng hạn Animal.copy():Animal và Dog.copy():Dog.

**6.** Nếu generic type parameter có bound `T extends Number`, bridge nhận Object hay Number?

**Đáp án:** Chữ ký sau erasure của T dùng Number, nên bridge cho override chuyên biệt nhận Number khi cần.

**Ghi nhớ:** **Bridge method là cầu nối bytecode do compiler tạo để quan hệ override trong Java source vẫn đúng sau erasure hoặc thay đổi kiểu trả về hiệp biến.** Khi gọi qua superclass/interface, JVM vẫn phân phối lời gọi đến phần cài đặt lớp con; bridge chuyển descriptor và có thể thực hiện cast cần thiết. Hiểu bridge giúp giải thích chính xác đa hình, unchecked calls, reflection và lỗi cast trong chương trình generic.
