# Đối chiếu generics trong Signature với descriptor sau erasure bằng javap

Khi biên dịch Java có **generics**, tệp `.class` thường chứa **hai cách mô tả kiểu** cho cùng một field, method hoặc class:

- **JVM descriptor**: mô tả kiểu ở mức máy ảo Java thực sự dùng để liên kết field, method và thực thi bytecode. Descriptor sử dụng kiểu sau **type erasure**, không giữ những đối số kiểu như `String` trong `List<String>`.
- **`Signature` attribute**: metadata bổ sung trong class file giúp ghi lại thông tin kiểu generic của **khai báo**: type variable, bound, parameterized type, wildcard, generic method hoặc generic superclass. Java reflection, compiler và công cụ phân tích bytecode có thể dựa vào metadata này để trình bày thông tin kiểu chi tiết.

Từ đó có hai kết luận phải giữ đồng thời: **generic type arguments phần lớn bị xóa khỏi descriptor và cơ chế thực thi**, nhưng **thông tin generic khai báo có thể được giữ lại ở `Signature` attribute**. Nói “generics biến mất hoàn toàn sau compile” là không chính xác; nói “JVM dùng `Signature` để kiểm tra từng phần tử của `List<String>` khi chạy” cũng sai.

Mục tiêu của bài là **kiểm chứng đầu ra biên dịch** bằng `javac`, `javap -s`, `javap -v`, Java Reflection API, và so sánh bridge method. Các ví dụ tương thích **Java 17+**; kết quả trọng tâm đã được kiểm chứng với **OpenJDK 21**.

## 1. Phân biệt ba khái niệm mang tên “signature”

Trong ngữ cảnh Java, từ “signature” có thể chỉ những thứ khác nhau:

| Thuật ngữ | Bản chất | Có chứa type arguments của generics không? |
| --- | --- | --- |
| **Java source method signature** | Khái niệm ngôn ngữ Java để phân biệt phương thức theo tên và các kiểu tham số (cùng các điều kiện quy định trong JLS) | Dùng quy tắc kiểu Java ở source; không phải chuỗi JVM descriptor |
| **JVM method descriptor** | Chuỗi mã hóa danh sách kiểu tham số + kiểu trả về trong `method_info` | **Không**; sử dụng kiểu JVM sau erasure |
| **Class-file `Signature` attribute** | Thuộc tính metadata có cú pháp generic signature riêng theo JVMS `4.7.9.1 | **Có**, khi khai báo sử dụng generic constructs và compiler phải phát attribute |

Ví dụ một phương thức nguồn:

~~~java
List<String> names(List<String> input)
~~~

Ở mức JVM, descriptor có dạng:

~~~text
(Ljava/util/List;)Ljava/util/List;
~~~

Còn `Signature` attribute của method có dạng:

~~~text
(Ljava/util/List<Ljava/lang/String;>;)Ljava/util/List<Ljava/lang/String;>;
~~~

Cả hai chuỗi đều hợp lệ và **nói về hai lớp thông tin khác nhau**. Đừng nhầm `Signature` attribute với Java source method signature dùng trong overload: Java **không** cho phép hai method chỉ khác kiểu trả về để trở thành hai overload thông thường, nhưng JVM method descriptor lại **có phần kiểu trả về**.

## 2. Type erasure ảnh hưởng đến kiểu như thế nào?

Theo Java Language Specification `4.6, erasure chuyển các kiểu generic của ngôn ngữ sang những kiểu có thể dùng tại JVM:

- `List<String>` và `List<Integer>` cùng erasure thành raw class/interface `List`.
- Một type variable không có bound tường minh, như `T` trong `class Box<T>`, có erasure là `Object`.
- Với `T extends Number`, erasure của `T` là `Number`.
- Với nhiều bounds, erasure dựa trên **leftmost bound**. Ví dụ `T extends Number & Comparable<T>` có erasure là `Number`.
- Với `U extends CharSequence`, erasure của `U` là `CharSequence`.
- Array chứa element type reference sau erasure vẫn là array; descriptor dùng ký tự `[`.
- Kiểu primitive không có generic parameterization, descriptor vẫn dùng ký hiệu primitive tương ứng.

**Erasure không đơn thuần xóa những dấu ngoặc `<...>` trong source rồi giữ mọi thứ khác nguyên trạng.** Compiler phải thay type variable bằng bound thích hợp; trong một số tình huống còn chèn cast và tạo bridge method để bảo toàn ngữ nghĩa của Java.

Ví dụ:

~~~java
class Box<T extends Number> {
    T value;
    T get() { return value; }
}
~~~

JVM không có một lớp runtime riêng `Box<Integer>` và một lớp `Box<Double>` do chính kiểu tham số ấy tạo ra. Field `value` và return type của `get()` ở descriptor được thể hiện bằng `java.lang.Number` vì bound của `T` là Number.

## 3. Cú pháp JVM descriptor: đọc đúng ký hiệu

Descriptor không dùng cú pháp tên Java thông thường. Nó là chuỗi ký hiệu được JVM Specification `4.3.2 và `4.3.3 định nghĩa.

### 3.1. Ký hiệu field descriptor

| Java type | Descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `java.lang.String` | `Ljava/lang/String;` |
| `java.util.List` | `Ljava/util/List;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| `int[][]` | `[[I` |

Tên class trong descriptor dùng dấu **`/`** để phân chia package nội bộ, không dùng dấu **`.`** như tên type trong Java source. Với reference type, dấu **`L`** mở tên class và dấu **`;`** kết thúc reference type.

`V` biểu diễn **void return** trong **method descriptor**, không phải kiểu của một field hợp lệ.

### 3.2. Ký hiệu method descriptor

Hình thức tổng quát:

~~~text
(DescriptorThamSố1DescriptorThamSố2...)DescriptorTrảVề
~~~

Ví dụ:

~~~java
static int sum(int a, int b) { return a + b; }
~~~

Descriptor:

~~~text
(II)I
~~~

Method:

~~~java
static void log(String value, int times) { }
~~~

Descriptor:

~~~text
(Ljava/lang/String;I)V
~~~

Method:

~~~java
static String[] convert(int[] values) {
    return new String[values.length];
}
~~~

Descriptor:

~~~text
([I)[Ljava/lang/String;
~~~

**Không có dấu phẩy hay tên tham số** giữa các thành phần descriptor. Một method generic như `<T> T identity(T t)` với bound ngầm Object sẽ có descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`, còn generic signature mang thông tin về `T`.

### 3.3. JVM descriptor được dùng để làm gì?

Descriptor tham gia định danh field/method trong class file và các symbolic references phục vụ linking/invocation. JVM dùng descriptor để biết số lượng, kiểu JVM của tham số và kiểu trả về; generic type arguments như `String` trong `List<String>` không đi vào cấu trúc này.

**Không được nhầm với kiểm tra kiểu source:** javac vẫn kiểm tra generic type arguments khi biên dịch Java. Một phần thông tin generic cũng được lưu lại để compiler khác có thể hiểu khai báo khi dùng class files làm dependency.

## 4. Ví dụ chính: một generic class có field, constructor và method

Tạo tệp **GenericSample.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericSample<T extends Number> {
    private T value;
    public List<String> labels;

    public GenericSample(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public List<T> copy(List<T> input) {
        return new ArrayList<>(input);
    }

    public <U extends CharSequence> U echo(U input) {
        return input;
    }

    public static void main(String[] args) {
        GenericSample<Integer> sample =
                new GenericSample<>(7);

        System.out.println(sample.get());
        System.out.println(sample.copy(List.of(3, 5)));
        System.out.println(sample.echo("ok"));
    }
}
~~~

Biên dịch bằng JDK 17+:

~~~bash
javac --release 17 -d out GenericSample.java
java -cp out GenericSample
~~~

**Standard output đã kiểm chứng:**

~~~text
7
[3, 5]
ok
~~~

Đây là source hoàn chỉnh, không cần thư viện ngoài JDK. `--release 17` chọn mức biên dịch Java 17; với javac 21, class file tạo ra có major version 61 thay vì 65 của target mặc định JDK 21. **Cú pháp descriptor và `Signature` về mặt generic trong ví dụ không đổi vì lựa chọn target này.**

### 4.1. Dùng javap -s xem descriptor

Chạy:

~~~bash
javap -classpath out -p -s GenericSample
~~~

Trong đó:

- **`-classpath out`** chỉ nơi chứa `GenericSample.class`.
- **`-p`** yêu cầu hiển thị cả private member (nếu không, field `value` có thể bị ẩn).
- **`-s`** yêu cầu in các **internal type signatures** theo cách gọi của tiện ích `javap`, tức các **JVM descriptors** xuất hiện sau dòng khai báo.
- **`-s` không phải công tắc in trực tiếp class-file `Signature` attribute** có generic syntax; để xem attribute ấy, dùng `-v`.

Các đoạn đầu ra quan trọng, đã đối chiếu với OpenJDK 21:

~~~text
private T value;
  descriptor: Ljava/lang/Number;

public java.util.List<java.lang.String> labels;
  descriptor: Ljava/util/List;

public GenericSample(T);
  descriptor: (Ljava/lang/Number;)V

public T get();
  descriptor: ()Ljava/lang/Number;

public java.util.List<T> copy(java.util.List<T>);
  descriptor: (Ljava/util/List;)Ljava/util/List;

public <U extends java.lang.CharSequence> U echo(U);
  descriptor: (Ljava/lang/CharSequence;)Ljava/lang/CharSequence;

public static void main(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)V
~~~

**Chú ý:** dòng khai báo được `javap` dựng lại có thể in `T` hoặc `List<String>` nhờ thông tin class file. **Dòng `descriptor:` ngay bên dưới** mới là giá trị descriptor JVM mà bài học cần đối chiếu. Đừng lấy việc header in generics làm bằng chứng rằng descriptor chứa generics.

### 4.2. Bảng đối chiếu từng declaration

| Khai báo Java | JVM descriptor | Vì sao |
| --- | --- | --- |
| `T value` | `Ljava/lang/Number;` | `T extends Number` xóa thành Number |
| `List<String> labels` | `Ljava/util/List;` | Type argument String không còn trong descriptor |
| `GenericSample(T value)` | `(Ljava/lang/Number;)V` | Constructor trả về void ở descriptor |
| `T get()` | `()Ljava/lang/Number;` | Return type T erases to Number |
| `List<T> copy(List<T>)` | `(Ljava/util/List;)Ljava/util/List;` | Generic arguments của List không ở JVM descriptor |
| `<U extends CharSequence> U echo(U)` | `(Ljava/lang/CharSequence;)Ljava/lang/CharSequence;` | U có erasure là CharSequence |
| `main(String[])` | `([Ljava/lang/String;)V` | Array của String và void return |

Việc đọc được descriptor chính xác giúp phát hiện một lỗi suy luận phổ biến: **`T extends Number` không erases to Object**. Chỉ type variable không bound tường minh hoặc bound thích hợp mới có Object làm erasure.

## 5. Dùng javap -v để xem Signature attribute

Chạy:

~~~bash
javap -classpath out -p -v GenericSample
~~~

Cờ **`-v`** in constant pool, attributes, code details và metadata; **`-p`** vẫn hữu ích để chắc chắn thấy private members.

Đầu ra dài, nên tìm mỗi declaration và các dòng **`descriptor:`**, **`Signature:`** bên dưới nó. Một đoạn đã kiểm chứng có dạng:

~~~text
private T value;
  descriptor: Ljava/lang/Number;
  Signature: #...                    // TT;

public java.util.List<java.lang.String> labels;
  descriptor: Ljava/util/List;
  Signature: #...                    // Ljava/util/List<Ljava/lang/String;>;

public GenericSample(T);
  descriptor: (Ljava/lang/Number;)V
  Signature: #...                    // (TT;)V

public T get();
  descriptor: ()Ljava/lang/Number;
  Signature: #...                    // ()TT;

public java.util.List<T> copy(java.util.List<T>);
  descriptor: (Ljava/util/List;)Ljava/util/List;
  Signature: #...                    // (Ljava/util/List<TT;>;)Ljava/util/List<TT;>;

public <U extends java.lang.CharSequence> U echo(U);
  descriptor: (Ljava/lang/CharSequence;)Ljava/lang/CharSequence;
  Signature: #...                    // <U::Ljava/lang/CharSequence;>(TU;)TU;
~~~

**Ký hiệu `#...` là vị trí constant-pool index minh họa**. Trong output thật, có các số `#19`, `#22`, v.v. Số thứ tự có thể thay đổi theo JDK, kiểu build và bố trí constant pool; **chuỗi phía sau comment `//` là phần có ý nghĩa về generic signature**.

Ở cuối output class còn có dòng class-level:

~~~text
Signature: #...                    // <T:Ljava/lang/Number;>Ljava/lang/Object;
~~~

Lưu ý class-level Signature xuất hiện **ngoài phần body các thành viên**, vì nó thuộc `ClassFile`. Còn các Signature ngay dưới field/method/constructor thuộc `field_info` hoặc `method_info` tương ứng.

### 5.1. Giải mã chuỗi Signature của field

Field `T value`:

~~~text
TT;
~~~

Ở generic signature grammar, chữ **`T`** đầu tiên mở một **type variable signature**, tên variable là **T**, kết thúc bằng **`;`**. Chuỗi này khác với JVM descriptor `Ljava/lang/Number;` vốn chỉ nêu erasure.

Field `List<String> labels`:

~~~text
Ljava/util/List<Ljava/lang/String;>;
~~~

Ở đây:

- `Ljava/util/List` biểu diễn reference class/interface List.
- `<...>` chứa type arguments ở dạng chữ ký generic.
- `Ljava/lang/String;` là argument String.
- Dấu `;` cuối đóng class-type signature của List.

Trong descriptor, toàn bộ thông tin argument nằm giữa `<` và `>` không xuất hiện:

~~~text
Ljava/util/List;
~~~

### 5.2. Giải mã chữ ký của method

Method `T get()`:

~~~text
descriptor: ()Ljava/lang/Number;
Signature:  ()TT;
~~~

Descriptor mô tả return type thực ở JVM là Number. Generic Signature nói rằng ở source return type là **type variable T**, được khai báo ở cấp class. Một caller với `GenericSample<Integer>` được compiler kiểm tra như lấy về Integer; việc này không làm JVM có method riêng cho Integer.

Method `copy`:

~~~text
descriptor: (Ljava/util/List;)Ljava/util/List;
Signature:  (Ljava/util/List<TT;>;)Ljava/util/List<TT;>;
~~~

Bên trong generic signature, `TT;` là type argument T cho cả parameter và result. JVM descriptor chỉ còn raw `List`.

Method `echo`:

~~~text
descriptor: (Ljava/lang/CharSequence;)Ljava/lang/CharSequence;
Signature:  <U::Ljava/lang/CharSequence;>(TU;)TU;
~~~

Đây là trường hợp có **generic method type parameter U**. Phần `<U::Ljava/lang/CharSequence;>` khai báo U có interface bound CharSequence. **Hai dấu hai chấm** ở đây không phải typo: grammar biểu thị class bound rỗng rồi interface bound `CharSequence`. Phần `(TU;)TU;` mã hóa U làm tham số và kiểu trả về.

### 5.3. Giải mã class-level signature

~~~text
<T:Ljava/lang/Number;>Ljava/lang/Object;
~~~

Ý nghĩa:

- `<T:Ljava/lang/Number;>` khai báo type parameter T với bound Number.
- `Ljava/lang/Object;` là generic superclass của GenericSample trong ví dụ.
- Chuỗi class signature có thể chứa thêm generic interfaces khi class triển khai interfaces tương ứng.

Đây là cách bytecode giữ lại **khai báo T extends Number** dù member descriptor chỉ có Number.

## 6. Signature không phải là một tên khác của descriptor

Mỗi field và method trong class file có **descriptor** mang cấu trúc bắt buộc để JVM hiểu loại member. Generic `Signature` là **attribute bổ sung**, xuất hiện khi khai báo cần thể hiện construct generic theo quy tắc của JVMS.

Đối chiếu:

| Tiêu chí | descriptor | Signature attribute |
| --- | --- | --- |
| Lưu ở đâu | `field_info.descriptor_index` / `method_info.descriptor_index` | Thuộc tính `Signature` trong danh sách attributes |
| Bắt buộc cho field/method class file | Có | Chỉ khi khai báo dùng các construct generic theo quy định |
| Chứa `<Ljava/lang/String;>` của `List<String>` | Không | Có |
| Chứa tên type variable `T` | Không; thay bằng erasure | Có thể chứa `TT;` |
| Dùng trực tiếp trong JVM linking / invocation | Có | Không để phân biệt những instantiation generic lúc runtime |
| Phục vụ generic reflection và compiler khác | Thông tin runtime type cơ sở | Có, lưu thông tin generic declarations |
| Có dạng `(args)return` cho method | Có | Có thể có thêm parameters và bounds ở đầu |
| Hiển thị tiện bằng javap | `javap -s` hoặc `-v` | `javap -v` |

**Không có Signature attribute** không tự chứng minh compiler đã làm sai. Một class/method/field không dùng type variable hoặc parameterized type có thể chỉ có descriptor. Ngược lại, với một generic declaration thuộc diện quy định, JVMS yêu cầu compiler tạo Signature tương ứng.

Theo JVMS `4.7.9, class file có tối đa **một Signature attribute** tại một vị trí `ClassFile`, `field_info`, `method_info` (và các trường hợp record component theo phiên bản đặc tả). Công cụ đọc class files phải xác định attribute thuộc member nào; không chỉ quét toàn bộ constant pool thấy từ “Signature” rồi đoán.

### 6.1. Signature được lưu qua constant pool như thế nào?

Bên trong class file, `Signature` attribute lưu index tới một `CONSTANT_Utf8_info` chứa chuỗi chữ ký. `javap -v` thường in:

~~~text
Signature: #68  // Ljava/util/List<Ljava/lang/String;>;
~~~

Chính `#68` là constant-pool reference ở một class file cụ thể, **không phải một mã Signature chuẩn hóa** để tra cứu mọi class file. Chuỗi ở bên phải mô tả type theo signature grammar.

Nếu viết một công cụ kiểm chứng bytecode, nên phân tích class file có cấu trúc hoặc dùng API đọc class file thích hợp thay vì chỉ tìm kiếm bằng regex trong stdout `javap`.

## 7. Vì sao erasure vẫn giữ được type safety ở source?

Giả sử:

~~~java
GenericSample<Integer> x = new GenericSample<>(7);
Integer number = x.get();
~~~

Tại source, javac kiểm tra bound `Integer extends Number`, rồi biết `get()` có return type T tương ứng với Integer trong ngữ cảnh `GenericSample<Integer>`. Nhưng ở bytecode, method `get()` vẫn có descriptor:

~~~text
()Ljava/lang/Number;
~~~

Compiler có thể chèn **`checkcast java/lang/Integer`** tại những điểm sử dụng giá trị cần Integer. Đó là một cơ chế thực thi để giữ kỳ vọng kiểu sau khi erasure. Tùy ngữ cảnh cụ thể, cast có thể được tối ưu hoặc được chèn tại caller; không nên giả định một câu lệnh println nhất định luôn chứa đúng một checkcast nếu chưa kiểm tra bytecode.

Để quan sát bytecode của chương trình đã biên dịch:

~~~bash
javap -classpath out -p -c GenericSample
~~~

`-c` disassemble code các method; tìm instruction `checkcast` nếu compiler phát sinh trong tình huống cụ thể. `javap -v` cũng bao gồm Code attribute nhưng chứa nhiều metadata hơn.

**Quan trọng:** runtime không bảo đảm collection List mang String chỉ vì field `labels` có Signature `List<String>`. Mã legacy/raw hoặc unchecked cast có thể phá vỡ type safety và gây `ClassCastException` về sau. Attribute Signature là **metadata của declaration**, không phải một validator quét từng phần tử collection ở mỗi thao tác.

## 8. Ví dụ riêng: erasure của bound đầu tiên

Thử các khai báo:

~~~java
class Bounds<T extends Number & Comparable<T>> {
    T data;
    T get() { return data; }
}
~~~

Ở đây `T` có hai bounds. Bound đầu tiên là `Number`, nên descriptor của `data` và return `get()` dùng `Number`. Generic signature vẫn có thể mã hóa cả hai bounds, trong đó `Comparable<T>` vẫn mang type argument T.

Một trường hợp khác:

~~~java
class Unbounded<T> {
    T data;
}
~~~

Vì T không khai báo bound tường minh, erasure của T là Object:

~~~text
descriptor: Ljava/lang/Object;
Signature:  TT;
~~~

Với interface bound:

~~~java
class RunnableBox<T extends Runnable> {
    T task;
}
~~~

`Runnable` là bound đầu tiên nên descriptor là `Ljava/lang/Runnable;`. Trong chữ ký generic, interface bound có cú pháp riêng; hãy dựa vào `javap -v` để thấy kết quả chính xác.

**Đọc descriptor dựa trên erasure của type variable theo JLS `4.6**, không theo giá trị object hoặc type argument được dùng tại một lời gọi cụ thể.

## 9. Wildcard: dấu +, -, * trong generic Signature

`Signature` attribute còn có cú pháp mã hóa **wildcards**:

| Source generic type | Phần generic signature điển hình | Giải thích |
| --- | --- | --- |
| `List<? extends Number>` | `Ljava/util/List<+Ljava/lang/Number;>;` | `+`: upper-bounded wildcard |
| `List<? super Integer>` | `Ljava/util/List<-Ljava/lang/Integer;>;` | `-`: lower-bounded wildcard |
| `List<?>` | `Ljava/util/List<*>;` | `*`: unbounded wildcard |
| `List<String>` | `Ljava/util/List<Ljava/lang/String;>;` | Type argument cụ thể |
| `List<T>` | `Ljava/util/List<TT;>;` | Type variable T |

**Tất cả những field kiểu `List<...>` trên đều có JVM field descriptor `Ljava/util/List;`**, dù nội dung generic signature khác nhau.

Đừng nhầm dấu `+` hoặc `-` của wildcard generic signature với arithmetic operators trong mã bytecode. Đây là ký hiệu của **signature grammar** theo JVMS `4.7.9.1, dùng để giữ ý nghĩa variance được diễn đạt qua wildcard ở Java source.

Đây cũng là bằng chứng vì sao chỉ đọc descriptor là **chưa đủ** khi xây dựng IDE hoặc tài liệu API muốn tái hiện wildcard của declaration.

## 10. Bridge method: hệ quả quan trọng của erasure

Generics và overriding cần duy trì đa hình sau erasure. Trong một số trường hợp, compiler sinh **bridge method**; việc kiểm chứng cả descriptor và flag của bridge là bài tập rất hữu ích.

Tạo tệp **Child.java**:

~~~java
class Parent<T> {
    public T get() {
        return null;
    }
}

public class Child extends Parent<String> {
    @Override
    public String get() {
        return "child";
    }

    public static void main(String[] args) {
        Parent<String> p = new Child();
        System.out.println(p.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -d out Child.java
java -cp out Child
~~~

**Stdout đã kiểm chứng trên OpenJDK 21:**

~~~text
child
~~~

### 10.1. Cùng tên get, hai descriptors trong Child

Trong Parent<T>, method nguồn `T get()` có erasure Object, nên ở `Parent.class`:

~~~text
descriptor: ()Ljava/lang/Object;
~~~

Trong Child, phương thức override khai báo return `String`. Khi dùng `javap -s`:

~~~bash
javap -classpath out -p -s Parent Child
~~~

Ở `Child.class`, bạn sẽ thấy **hai method có tên get** với descriptors khác nhau:

~~~text
public java.lang.String get();
  descriptor: ()Ljava/lang/String;

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
~~~

Đối với Java source, hai phương thức được thấy là một public override hợp lệ và một bridge do compiler tạo, không phải hai overload source mà programmer tự khai báo dựa vào return type. Dòng `get():Object` trong class file giúp lời gọi thông qua `Parent` vẫn dispatch tới implementation trong Child.

### 10.2. Flag ACC_BRIDGE và ACC_SYNTHETIC

Chạy:

~~~bash
javap -classpath out -p -v Child
~~~

Phần bridge sẽ có dạng:

~~~text
public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
  Code:
     0: aload_0
     1: invokevirtual #...  // Method get:()Ljava/lang/String;
     4: areturn
~~~

Số `#...` là constant-pool index có thể thay đổi. Ý nghĩa:

- **ACC_BRIDGE**: method cầu nối do compiler sinh để hỗ trợ quan hệ overriding sau generic erasure/covariant return.
- **ACC_SYNTHETIC**: method không xuất hiện nguyên vẹn trong source code người dùng.
- Bridge trả về Object và gọi implementation `String get()` thực sự trong Child.
- Bridge có **descriptor riêng**, vì JVM cần đúng method descriptor ở điểm gọi/linking.

**Bridge không phải dấu hiệu compiler sai hay một generic instantiation mới.** Nó là kỹ thuật compiler duy trì polymorphism theo quy tắc Java. Khi dùng Reflection API `getDeclaredMethods()`, có thể nhìn thấy cả bridge; `Method.isBridge()` và `isSynthetic()` giúp phân loại.

### 10.3. Vì sao chỉ so Signature với descriptor chưa đủ trong override?

Nếu chỉ xem một method ở Child, người học có thể hỏi vì sao `get()` có cả return String và Object. Cần hiểu **class hierarchy, erased parent method descriptor và bridge method**. Vì thế kiểm chứng generic output có lúc cần xem nhiều tệp class chứ không chỉ một class file.

Không được gọi bridge method là “method generic có Signature chứa String” một cách máy móc. Bridge trong ví dụ có descriptor `()Ljava/lang/Object;` và flag bridge; nó không cần một Signature attribute generic như khai báo source `Parent<T>.get()`.

## 11. Reflection: type đã xóa và generic declaration khác nhau

Java Reflection API hỗ trợ cả cách đọc type theo JVM/erasure và cách đọc type generic declaration.

Với `GenericSample.java` ở phần 4, tạo **ReflectProbe.java**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;

public class ReflectProbe {
    public static void main(String[] args) throws Exception {
        Field field =
                GenericSample.class.getField("labels");

        System.out.println(
                "field type=" + field.getType().getTypeName()
        );
        System.out.println(
                "field generic=" +
                field.getGenericType().getTypeName()
        );

        Method getter =
                GenericSample.class.getMethod("get");

        System.out.println(
                "return type=" +
                getter.getReturnType().getTypeName()
        );
        System.out.println(
                "return generic=" +
                getter.getGenericReturnType().getTypeName()
        );

        TypeVariable<?> variable =
                GenericSample.class.getTypeParameters()[0];

        System.out.println(
                "type variable=" + variable.getName()
        );
        System.out.println(
                "bound=" +
                variable.getBounds()[0].getTypeName()
        );
    }
}
~~~

Biên dịch và chạy (phải có cả `GenericSample.java`):

~~~bash
javac --release 17 -d out GenericSample.java ReflectProbe.java
java -cp out ReflectProbe
~~~

**Standard output đã kiểm chứng trên OpenJDK 21:**

~~~text
field type=java.util.List
field generic=java.util.List<java.lang.String>
return type=java.lang.Number
return generic=T
type variable=T
bound=java.lang.Number
~~~

Các cặp đặc biệt quan trọng:

- `Field.getType()` trả **raw Class object** `List.class` tương ứng với descriptor `Ljava/util/List;`.
- `Field.getGenericType()` trả thông tin type `List<String>`, là phần khai báo được lưu trong generic metadata.
- `Method.getReturnType()` trả `Number.class` cho `T get()` vì erasure của T là Number.
- `Method.getGenericReturnType()` có thể trả đối tượng `TypeVariable` mang tên T.
- `Class.getTypeParameters()` cho phép đọc khai báo type parameter và bound.

**Không hiểu sai Reflection:** kết quả `getGenericType()` cho bạn biết **field được khai báo là List<String>**, không chứng minh mọi object mà field trỏ tới thực sự chứa String. `ArrayList<String>` và `ArrayList<Integer>` không là hai class runtime khác nhau chỉ vì generic arguments.

### 11.1. Generic superclass và object instance

Nếu source có:

~~~java
class IntegerBox extends GenericSample<Integer> {
    IntegerBox() {
        super(1);
    }
}
~~~

Đây là **đoạn class minh họa**, đặt cùng project và biên dịch với `GenericSample.java`. `IntegerBox.class.getGenericSuperclass()` có thể cho thấy type argument Integer vì khai báo **extends GenericSample<Integer>** được ghi vào class-level Signature của IntegerBox.

Ngược lại, nếu chỉ tạo:

~~~java
GenericSample<Integer> instance =
        new GenericSample<>(1);
~~~

thì `instance.getClass()` là `GenericSample.class`, và **không mang một class runtime riêng cho Integer**. Thông tin về type argument trong **biến sử dụng** không nhất thiết được giữ thành thuộc tính trên object tại runtime.

## 12. Descriptor dùng trong liên kết; Signature hỗ trợ generic reflection

Một cách nhìn khái niệm:

~~~text
GenericSample<T extends Number>  (Java source)
                  |
                  v
              javac
                  |
                  +-- JVM descriptors
                  |     field value: Ljava/lang/Number;
                  |     get(): ()Ljava/lang/Number;
                  |     labels: Ljava/util/List;
                  |
                  +-- Signature attributes
                        field value: TT;
                        get(): ()TT;
                        labels: Ljava/util/List<Ljava/lang/String;>;
                        class: <T:Ljava/lang/Number;>Ljava/lang/Object;
                  |
                  v
              .class file
                  |
                  +-- JVM uses descriptors for type/linking/invocation
                  +-- compiler/reflection/tooling reads generic metadata
~~~

Theo JVMS, Signature attribute có chức năng **hỗ trợ reflection, debugging và việc biên dịch khi chỉ còn class files**. JVM không cần dùng type arguments của Signature để tạo các specialized versions của class theo String/Integer.

Với class files được tạo hoặc chỉnh sửa bởi công cụ khác, **generic Signature có thể sai/malformed** dù descriptor vẫn tồn tại. Tài liệu JVMS nêu việc kiểm tra tính hợp lệ Signature có thể diễn ra khi các Java SE library methods truy cập generic metadata; vì vậy khi xây dựng tool đọc bytecode, không coi mọi Signature từ file không tin cậy là luôn hợp lệ.

## 13. Đọc local variables: khác Signature attribute cấp field/method

`Signature` gắn vào class, field, method hoặc record component không phải cơ chế metadata duy nhất liên quan generics. Local variables trong method có thể có thông tin debug:

- **LocalVariableTable**: tên, slot và descriptor của biến cục bộ trong phạm vi bytecode.
- **LocalVariableTypeTable**: generic type signatures của một số local variables khi compiler phát đủ metadata.

Ví dụ:

~~~java
// Minh họa mã bên trong một method.
List<String> words = List.of("a", "b");
System.out.println(words.size());
~~~

Nếu bật debug metadata phù hợp:

~~~bash
javac -g -d out GenericSample.java
javap -classpath out -v -p GenericSample
~~~

Bạn có thể kiểm tra các debug attributes **nếu source thực sự chứa local variable cần xem**. Lệnh trên với source `GenericSample.java` ban đầu có một số locals khác nhưng không chứa biến `words` của fragment minh họa. Muốn thấy `words`, phải **thêm fragment vào một method thật** trước khi compile. Không giả định mọi biến cục bộ generic sẽ luôn có `LocalVariableTypeTable` nếu compiler không được yêu cầu phát metadata hoặc tối ưu/cấu trúc code khác nhau.

**Đừng lẫn `LocalVariableTypeTable` với `Signature` cấp member.** Một tool chỉ tra field/method Signature sẽ không tự phục hồi mọi generic type của local variables.

## 14. Đối chiếu kết quả với javap theo một quy trình lặp lại

Một lộ trình kiểm chứng class files sau compile:

1. **Lưu phiên bản source:** biết khai báo nào đang được kiểm tra, đừng dùng class file cũ.
2. **Biên dịch với output riêng:** ví dụ `javac --release 17 -d out ...`.
3. **Đọc class-level summary:** `javap -classpath out -p GenericSample` để biết member công khai và private.
4. **Đọc descriptor:** `javap -classpath out -p -s GenericSample`.
5. **Đọc Signature attribute:** `javap -classpath out -p -v GenericSample`.
6. **Ghép theo đúng member:** field `labels` với field `labels`, method `copy` với method `copy`.
7. **Áp dụng erasure rules:** giải thích vì sao kiểu JVM là raw List/Number/Object.
8. **Kiểm tra generic metadata:** xác định type parameter, bounds và type arguments còn ở Signature.
9. **Nếu có override generic:** xem thêm superclass/subclass và bridge methods.
10. **Khi cần runtime proof:** gọi `Field.getGenericType()` và `Method.getGenericReturnType()`.
11. **Chốt QA:** class file đã biên dịch thành công; output được đọc từ đúng thư mục, đúng class và đúng JDK.

### 14.1. Cách nhận biết kết quả đúng

Với `GenericSample.java` đã đưa, một lần kiểm chứng đạt yêu cầu cần đồng thời xác nhận:

- Field `value`: descriptor `Ljava/lang/Number;`, Signature `TT;`.
- Field `labels`: descriptor `Ljava/util/List;`, Signature `Ljava/util/List<Ljava/lang/String;>;`.
- Constructor: descriptor `(Ljava/lang/Number;)V`, generic Signature `(TT;)V`.
- Method `get`: descriptor `()Ljava/lang/Number;`, Signature `()TT;`.
- Method `copy`: descriptor `(Ljava/util/List;)Ljava/util/List;`, Signature có `List<T>` ở parameter và result.
- Method `echo`: descriptor lấy `CharSequence`, Signature khai báo generic U.
- Class-level Signature có `<T:Ljava/lang/Number;>Ljava/lang/Object;`.
- Program stdout `7`, `[3, 5]`, `ok` như phần 4.

Chỉ cần `javap -s` là **không đủ** để xác nhận các generic Signature attributes. Chỉ cần `javap -v` mà không đối chiếu từng dòng descriptor/member cũng dễ diễn giải nhầm.

## 15. Những lỗi suy luận phổ biến

**Sai lầm 1 — “Ở bytecode hoàn toàn không còn generics.”**

Sai vì `Signature` attribute có thể lưu đầy đủ phần generic declaration. Đúng hơn: **JVM descriptor và phần lớn hoạt động runtime sử dụng erased types**, còn compiler/tooling/reflection có thể đọc lại generic metadata.

**Sai lầm 2 — “javap -s là lệnh duy nhất xem generic Signature.”**

Sai. `javap -s` in internal JVM descriptors; khi muốn thấy attribute mang tên `Signature` dùng `javap -v` và quan sát đúng thành viên.

**Sai lầm 3 — “T với bound Number vẫn biến thành Object.”**

Sai. Erasure lấy **leftmost bound**, nên `T extends Number` thành Number. Chỉ với T không bound tường minh, erasure mới thường là Object.

**Sai lầm 4 — “Hai List có type arguments khác nhau tạo hai kiểu JVM descriptor.”**

Sai. `List<String>` và `List<Integer>` cùng có erased field descriptor `Ljava/util/List;`; generic Signature khác khi khai báo khác.

**Sai lầm 5 — “Signature là bộ luật runtime kiểm tra từng phần tử.”**

Sai. `Signature` là metadata; collection generic không tự trở thành container được JVM chuyên biệt hóa theo String. Raw/unchecked code vẫn có thể gây heap pollution.

**Sai lầm 6 — “Hai method get trong Child là hai overload Java source do tôi viết.”**

Sai. Trong ví dụ `Child` chỉ viết một `String get()`; compiler tạo bridge `Object get()` để đảm bảo polymorphism sau erasure.

**Sai lầm 7 — “Mọi class file phải có Signature.”**

Sai. Member không dùng construct generic không nhất thiết có Signature. JVM descriptor là phần cấu trúc cơ bản hơn.

**Sai lầm 8 — “Số #68 trong javap có ý nghĩa generic cố định.”**

Sai. Nó là **index tới constant pool của class file cụ thể**. Chuỗi encoded signature mới là thông tin semantic cần giải mã.

**Sai lầm 9 — “Nếu Reflection đọc List<String>, object chắc chắn chỉ chứa String.”**

Sai. `Field.getGenericType()` nói về khai báo; không xác minh toàn bộ giá trị runtime hoặc những aliases có raw type.

**Sai lầm 10 — “Có Signature generic thì method overload chỉ cần khác kiểu trả về.”**

Sai. Java source không cho overload chỉ bởi return type. JVM descriptors chứa return type cho cơ chế class file và method linking; đó là cấp quy tắc khác với Java source overload.

## 16. Bài tập tự thực hành

### Bài 1 — Nhận diện descriptor

Từ các kiểu Java sau, viết JVM field descriptors rồi dùng javap kiểm tra:

- `int`.
- `long`.
- `String[]`.
- `List<String>`.
- `List<? extends Number>`.
- `T` trong `class Holder<T extends Number>`.

Giải thích tại sao hai trường List dùng cùng descriptor nhưng Signature có thể khác.

### Bài 2 — Đổi bound

Thay `class GenericSample<T extends Number>` thành một class khác `GenericSample<T>` và sửa code cho phù hợp. Dự đoán descriptor của field `value` và method `get` đổi từ Number sang kiểu nào; xác minh bằng `javap -s` và `-v`.

### Bài 3 — Wildcard

Tạo class có ba field `List<? extends Number>`, `List<? super Integer>` và `List<?>`. Biên dịch rồi tìm lần lượt ký hiệu `+`, `-`, `*` ở `Signature`. Kiểm tra rằng descriptor của cả ba vẫn là `Ljava/util/List;`.

### Bài 4 — Bridge method

Biên dịch `Child.java` ở phần 10. Dùng `javap -v -p` xác định tên, descriptor và flags của phương thức bridge. Dự đoán output khi gọi `Parent<String> p = new Child(); p.get()`.

### Bài 5 — Reflection

Chạy `ReflectProbe.java`, giải thích vì sao `field.getType()` trả raw List còn `field.getGenericType()` trả List<String>. Kiểm tra tương tự với `getReturnType()` và `getGenericReturnType()` của `get()`.

### Bài 6 — Mô tả chính xác một kết quả

Cho hai dòng:

~~~text
descriptor: (Ljava/util/List;)Ljava/util/List;
Signature:  (Ljava/util/List<TT;>;)Ljava/util/List<TT;>;
~~~

Viết giải thích ngắn cho người học: JVM thấy một method nhận/trả List, trong khi generic metadata diễn đạt List<T> ở cả đầu vào/đầu ra. Không được viết rằng JVM tự kiểm tra mọi phần tử là T tại runtime.

### Bài 7 — Audit class file không có source

Bạn chỉ nhận một `.class` từ thư viện. Dùng `javap -v` xác định generic superclass, fields và method signatures. Nêu những gì **có thể xác minh** bằng class file và những điều **không thể suy ra**, ví dụ type argument của một object instance mà chương trình tạo sau này.

## 17. Câu hỏi tự kiểm tra

1. Descriptor JVM khác `Signature` attribute ở mục đích và nơi lưu trữ thế nào?
2. Vì sao `List<String>` có descriptor `Ljava/util/List;`?
3. Với `T extends Number`, erasure của T là Object hay Number?
4. `TT;` mã hóa điều gì trong generic signature?
5. `<U::Ljava/lang/CharSequence;>` có hai dấu hai chấm vì sao?
6. `javap -s` và `javap -v` cần dùng khác nhau như thế nào?
7. Vì sao `GenericSample<Integer>` không làm JVM tạo riêng class GenericSampleInteger?
8. Reflection đọc generic Signature cho biết declaration hay đảm bảo giá trị runtime?
9. Khi nào compiler cần bridge method? Flags nào giúp nhận diện?
10. Tại sao có hai descriptors `get():Object` và `get():String` trong `Child.class`?
11. `LocalVariableTypeTable` khác gì `Signature` của field hoặc method?
12. Nếu `Signature` vắng mặt, có nhất thiết là class file hỏng không?
13. Làm sao đảm bảo `javap` đang đọc đúng class file mới vừa biên dịch?
14. Vì sao không nên dùng số constant-pool index làm tiêu chí so sánh giữa các builds?

## 18. Nguồn tham khảo chính thức

- **JLS 21 `4.6 — Type Erasure:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6
- **JVMS 21 `4.3.2 — Field Descriptors:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.2
- **JVMS 21 `4.3.3 — Method Descriptors:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3
- **JVMS 21 `4.7.9 — Signature Attribute:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9
- **JVMS 21 `4.7.9.1 — Generic Signatures:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9.1
- **Oracle JDK 21 — javap Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- **Java SE 21 — Field.getGenericType:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html
- **Java SE 21 — Method.getGenericReturnType:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html

**Ghi nhớ:** Muốn kiểm chứng generics đã được biên dịch, hãy **đặt `descriptor` và `Signature` cạnh nhau trên đúng field/method/class**. Descriptor thể hiện **erased JVM types**; Signature giữ **generic declaration metadata** để compiler, reflection và tooling hiểu type variables/arguments/bounds. Dùng `javap -s` để thấy descriptor, `javap -v -p` để thấy cả Signature và bridge flags, và dùng Reflection để kiểm tra thông tin generic ở mức khai báo.