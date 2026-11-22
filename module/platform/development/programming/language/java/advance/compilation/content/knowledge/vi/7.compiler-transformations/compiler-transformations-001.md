# Type erasure và sự khác nhau giữa kiểu nguồn với JVM descriptor

## 1. Bức tranh tổng thể: ba cách nhìn một khai báo

Java cho phép viết kiểu có tham số, chẳng hạn `List<String>`, `Box<Integer>` và `<T extends Number> T get(T value)`. Ở **mã nguồn**, các kiểu này giúp trình biên dịch kiểm tra sự an toàn kiểu, suy luận kiểu, chọn phương thức, kiểm soát chuyển đổi và phát hiện lỗi trước khi chạy. Khi `javac` biên dịch, phần lớn cấu trúc generic được **erasure** (xóa tham số kiểu) để tạo các kiểu mà máy ảo Java có thể thao tác qua field/method **descriptor**.

Ba khái niệm cần tách rõ:

| Tầng | Nó mô tả gì? | Ví dụ |
| --- | --- | --- |
| **Kiểu nguồn (source-level type)** | Kiểu trong Java Language Specification (JLS), bao gồm tham số kiểu, wildcard, ràng buộc và type variable | `List<String>`, `T extends Number` |
| **Descriptor trong class file** | Biểu diễn trường/tham số/kiểu trả về mà JVM dùng để nhận diện thành viên và liên kết lời gọi | `Ljava/util/List;`, `()Ljava/lang/Number;` |
| **Generic signature (`Signature` attribute)** | Metadata riêng có thể bảo tồn khai báo generic cho compiler, reflection và công cụ | `Ljava/util/List<Ljava/lang/String;>;`, `()TT;` |

**Điểm cốt lõi:** *descriptor* và *generic signature* là hai cấu trúc khác nhau. Descriptor dùng ngữ pháp JVM và không mã hóa `List<String>` như một kiểu thực thi riêng. Một `Signature` attribute có thể ghi lại tham số generic ở mức khai báo, dù descriptor đã erasure. Generic signature **không** biến thành kiểm tra tham số kiểu tự động đối với từng đối tượng ở runtime.

Bài này tập trung vào sự khác biệt giữa kiểu nguồn và descriptor do `javac` sinh ra, kèm phương pháp quan sát bằng `javap` trên JDK 17+.

## 2. Quy tắc type erasure theo JLS `4.6

Erasure là phép ánh xạ một kiểu (có thể chứa tham số kiểu hoặc type variable) thành kiểu **không có** tham số kiểu/type variable. Với các tình huống cơ bản:

1. **Parameterized type:** erasure của `G<A, B>` là erasure của `G`. Ví dụ `List<String>`, `List<Integer>` và `List<? extends Number>` cùng thành `List` về mặt erasure.
2. **Type variable không ghi bound:** `T` ngầm có bound `Object` nên erasure là `Object`.
3. **Type variable có bound:** `T extends Number` thành `Number`. Với `T extends Number & Comparable<T>`, erasure dựa trên **bound đầu tiên**, tức `Number`.
4. **Type variable có interface bound đầu tiên:** `T extends Comparable<T> & java.io.Serializable` thành `Comparable`; không tự biến thành `Object` hoặc một kiểu kết hợp ở JVM.
5. **Array:** erasure áp dụng lên kiểu phần tử: `T[]` thành `Object[]` nếu `T` không có bound; `List<String>[]` về mức biểu diễn kiểu thành `List[]` (nhưng cách tạo generic array có quy tắc hạn chế riêng).
6. **Kiểu không có tham số kiểu/type variable:** giữ nguyên, chẳng hạn `int`, `String` và `Number`.

Ví dụ đối chiếu:

| Kiểu nguồn | Kiểu sau erasure | Field descriptor tương ứng |
| --- | --- | --- |
| `String` | `String` | `Ljava/lang/String;` |
| `List<String>` | `List` | `Ljava/util/List;` |
| `Map<String, Integer>` | `Map` | `Ljava/util/Map;` |
| `T` (unbounded) | `Object` | `Ljava/lang/Object;` |
| `T extends Number` | `Number` | `Ljava/lang/Number;` |
| `T extends Number & Runnable` | `Number` | `Ljava/lang/Number;` |
| `List<String>[]` | `List[]` | `[Ljava/util/List;` |
| `T[]` với `T extends Number` | `Number[]` | `[Ljava/lang/Number;` |
| `int[]` | `int[]` | `[I` |

**Phân biệt erasure với “xóa hết kiểm tra kiểu”.** Kiểm tra `List<String>` có nhận một `Integer` hay không diễn ra ở compile time, theo quy tắc generic của ngôn ngữ. Sau compile, bytecode có thể cần thêm `checkcast` để bảo toàn kiểu mà mã nguồn đã dựa vào. Erasure không khiến Java bỏ qua lỗi generic ngay trong code nguồn hợp lệ.

## 3. Descriptor của JVM: ngữ pháp và cách đọc

JVM định nghĩa field descriptor ở JVMS `4.3.2 và method descriptor ở `4.3.3. Descriptor là chuỗi ký hiệu cô đọng, **khác hẳn cú pháp nguồn Java**.

| Java type | JVM descriptor | Ý nghĩa |
| --- | --- | --- |
| `byte` | `B` | primitive 8 bit |
| `char` | `C` | primitive ký tự |
| `double` | `D` | primitive double |
| `float` | `F` | primitive float |
| `int` | `I` | primitive int |
| `long` | `J` | primitive long |
| `short` | `S` | primitive short |
| `boolean` | `Z` | primitive boolean |
| `void` (chỉ vị trí return của method descriptor) | `V` | không trả về giá trị |
| `java.lang.String` | `Ljava/lang/String;` | object/class, tên nội bộ dùng dấu `/` |
| `java.util.List` | `Ljava/util/List;` | interface/class |
| `int[]` | `[I` | mảng một chiều |
| `String[][]` | `[[Ljava/lang/String;` | mảng hai chiều |

Ví dụ định nghĩa method descriptor có dạng:

```text
(DescriptorCuaThamSo1 DescriptorCuaThamSo2 ...) DescriptorTraVe
```

Không có dấu phẩy giữa các tham số. Phần `(...)` chứa **tham số thực ở tầng JVM**, sau `)` là kiểu trả về; tên method được lưu riêng trong class file.

| Khai báo Java | Descriptor |
| --- | --- |
| `void ping()` | `()V` |
| `int sum(int left, int right)` | `(II)I` |
| `String get(String[] values, int i)` | `([Ljava/lang/String;I)Ljava/lang/String;` |
| `List<String> parse(String input)` | `(Ljava/lang/String;)Ljava/util/List;` |
| `T id(T value)` với `T` unbounded | `(Ljava/lang/Object;)Ljava/lang/Object;` |
| `T id(T value)` với `T extends Number` | `(Ljava/lang/Number;)Ljava/lang/Number;` |

Descriptor **chứa kiểu trả về**. Đây là điểm khác cách JLS định nghĩa *method signature* ở mức nguồn (tên, tham số kiểu và kiểu tham số sau các quy tắc tương ứng; **không** dùng kiểu trả về để phân biệt hai overload trong Java). JVM có thể chứa các method có cùng tên và tham số nhưng descriptor khác ở kiểu trả về; `javac` đôi khi cần khả năng này để sinh *bridge method*. Đừng trộn lẫn thuật ngữ *method signature trong JLS*, *method descriptor trong JVMS* và *generic `Signature` attribute* chỉ vì đều chứa từ “signature”.

Trong tên nội bộ JVM, dấu `/` ngăn các thành phần package: `java.lang.String` được viết `java/lang/String` bên trong descriptor. Với lớp lồng nhau, tên binary thường có `$`, ví dụ `LErasureLab$Box;`, thay vì cú pháp source `ErasureLab.Box`.

## 4. Ví dụ runnable: một file chứng minh erasure, cast và bridge

Tạo file tên **`ErasureLab.java`** dưới thư mục đang làm việc:

```java
import java.lang.reflect.Method;
import java.util.List;

public class ErasureLab {
    static class Box<T extends Number> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static class Parent<T> {
        T get() {
            return null;
        }
    }

    static class Child extends Parent<String> {
        @Override
        String get() {
            return "child";
        }
    }

    static <T> T same(T value) {
        return value;
    }

    static void accept(List<String> values) {
        System.out.println(values.get(0));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Box<Integer> box = new Box<>(7);
        Integer number = box.get();
        String text = same("hello");
        Parent<String> parent = new Child();

        accept(List.of("java"));
        System.out.println(number);
        System.out.println(text);
        System.out.println(parent.get());

        long bridges = 0;
        for (Method method : Child.class.getDeclaredMethods()) {
            if (method.isBridge()) {
                bridges++;
            }
        }
        System.out.println("bridge=" + bridges);

        Method method = ErasureLab.class.getDeclaredMethod(
                "accept", List.class);
        System.out.println(
                "descriptorParam=" + method.getParameterTypes()[0].getTypeName());
        System.out.println(
                "genericParam=" + method.getGenericParameterTypes()[0].getTypeName());
    }
}
```

Dùng JDK 17+ và biên dịch bằng release 17:

```bash
javac --release 17 -d out ErasureLab.java
java -cp out ErasureLab
```

**Stdout chính xác:**

```text
java
7
hello
child
bridge=1
descriptorParam=java.util.List
genericParam=java.util.List<java.lang.String>
```

Ví dụ này được kiểm tra với `javac` JDK 21. Các phần cần chú ý:

- `Box<T extends Number>` có field kiểu nguồn `T`, nhưng field descriptor dùng `Number`.
- `Box<Integer>` trả về `Integer` tại lời gọi ở mã nguồn; khi bytecode gọi `Box.get()` nhận kết quả mức JVM là `Number`, compiler có thể chèn `checkcast java/lang/Integer` để thỏa kiểu nguồn `Integer`.
- `same(T)` có type variable không bound, nên descriptor tham số và kết quả là `Object`; lời gọi gán cho `String` cũng cần kiểm tra cast khi cần.
- `Parent<T>.get()` sau erasure trả `Object`; `Child.get()` trả `String` ở source. Compiler sinh thêm **bridge method** trả `Object` để lời gọi qua kiểu `Parent<String>` tiếp tục dispatch đúng.
- `accept(List<String>)` có tham số descriptor là `List`, nhưng generic metadata vẫn có thể mô tả `List<String>` để reflection đọc qua `getGenericParameterTypes()`.

Phần tiếp theo sẽ khảo sát class file sinh ra và giải thích từng điểm.

## 5. Dùng javap kiểm chứng descriptor và generic Signature

`javap` là công cụ của JDK dùng để phân tích class file. Nó **không** sửa source code hoặc biên dịch lại; nó đọc artifact đã tạo.

Sau khi biên dịch ví dụ `ErasureLab.java`, chạy:

```bash
javap -s -p -classpath out ErasureLab
javap -s -p -classpath out 'ErasureLab$Box'
javap -s -p -classpath out 'ErasureLab$Child'
```

Dấu nháy đơn quanh tên `ErasureLab$Box` và `ErasureLab$Child` tránh việc một số shell diễn giải ký tự `$` như tên biến. Ví dụ lệnh hoạt động với shell POSIX và PowerShell; trên Windows CMD có thể dùng dấu nháy kép. Tệp class thực sự là `ErasureLab$Box.class`, `ErasureLab$Child.class`.

### 5.1. Field và method của Box

Phần liên quan trong `javap -s -p -classpath out 'ErasureLab$Box'`:

```text
private T value;
  descriptor: Ljava/lang/Number;
ErasureLab$Box(T);
  descriptor: (Ljava/lang/Number;)V
T get();
  descriptor: ()Ljava/lang/Number;
```

Dòng hiển thị kiểu `T` là dạng trình bày của `javap`, còn dòng **`descriptor`** là kiểu mà JVM dùng. Không được suy ra có một “JVM object kiểu T” từ việc `javap` có thể hiển thị tên type variable.

Khi dùng chế độ chi tiết:

```bash
javap -v -p -classpath out 'ErasureLab$Box'
```

Có thể tìm các đoạn khai báo tương ứng với `Signature` attribute, về mặt cấu trúc:

```text
field value:
  descriptor: Ljava/lang/Number;
  Signature: TT;

method get:
  descriptor: ()Ljava/lang/Number;
  Signature: ()TT;
```

Đây là **tóm tắt các giá trị liên quan**, không phải bản sao nguyên văn toàn bộ output `javap -v`. Trong output thực, `javap` có thêm constant pool index, flags, instruction và vị trí attribute.

### 5.2. Method parameterized List

Với khai báo:

```java
static void accept(List<String> values) { ... }
```

Phần liên quan:

```text
descriptor: (Ljava/util/List;)V
Signature: (Ljava/util/List<Ljava/lang/String;>;)V
```

Đây là ví dụ trực tiếp cho chủ đề bài học:

- **Nguồn:** `List<String>`, giúp compiler ngăn truyền kiểu phần tử không phù hợp.
- **Descriptor:** `Ljava/util/List;`, không chứa `String`.
- **Signature attribute:** mã hóa thêm type argument `String` cho mục đích phản chiếu và các công cụ hiểu generic.

Không cần biết số index của constant pool; chỉ cần đối chiếu hai giá trị. Nếu chỉ xem `javap -s`, bạn có thể thấy descriptor mà chưa thấy generic signature chi tiết. Dùng `-v` để đọc attributes và `-c` để xem instruction.

### 5.3. Lời gọi và cast trong bytecode

```bash
javap -c -p -classpath out ErasureLab
```

Tìm vùng mã của `main`. Với lệnh gán:

```java
Integer number = box.get();
String text = same("hello");
```

Trình biên dịch cần bảo đảm kết quả của các lời gọi đã erasure khớp kỳ vọng kiểu ở source. Bạn thường thấy các instruction tương ứng với `checkcast java/lang/Integer` và `checkcast java/lang/String` sau khi invoke phương thức có descriptor trả `Number` hoặc `Object`. Vị trí offset và thứ tự chi tiết các instruction là đầu ra của compiler cụ thể, không phải quy tắc bắt buộc mọi Java compiler phải phát nguyên chuỗi bytecode giống nhau.

**Cast sinh ra bởi compiler không phải cast vô nghĩa.** Nếu bytecode thật sự nhận một đối tượng không phù hợp tại vị trí mà source dựa vào `Integer` hoặc `String`, cast có thể ném `ClassCastException`.

## 6. Generic Signature attribute: lưu metadata, không reify mỗi instance

JVMS `4.7.9 định nghĩa attribute tên **`Signature`**, còn `4.7.9.1` định nghĩa ngữ pháp chữ ký generic. Trình biên dịch Java ghi generic signature trong các khai báo áp dụng theo quy tắc JVMS: lớp generic, method generic, thành viên có type variable/parameterized type, v.v.

Đối với `Box<T extends Number>`, generic signature của **class** diễn tả rằng type variable `T` có bound `Number` và lớp kế thừa `Object`, về dạng:

```text
<T:Ljava/lang/Number;>Ljava/lang/Object;
```

Các ký hiệu khác nhau:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `Ljava/lang/Number;` trong **descriptor** | Reference type có tên `java.lang.Number` ở runtime |
| `T` trong nguồn | Type variable tên `T`, được compiler kiểm tra theo bound |
| `TT;` trong **generic signature grammar** | Tham chiếu tới type variable tên `T` |
| `Ljava/util/List<Ljava/lang/String;>;` trong **generic signature** | Một parameterized type `List<String>` ở mức metadata |

**Không đem ngữ pháp của Signature attribute đọc như descriptor.** `TT;` là TypeVariableSignature, **không phải** một field descriptor hợp lệ. Ngược lại, `Ljava/util/List;` là descriptor của reference type `List`, nhưng không ghi được phần `<String>`.

Generic signature giúp compiler sau này đọc type information khi biên dịch mã phụ thuộc vào một class file, và giúp Java reflection trả về các khai báo generic như `Method.getGenericParameterTypes()`, `Field.getGenericType()` hoặc `Class.getGenericSuperclass()`. Reflection **không thể** từ mọi đối tượng `new Box<Integer>(7)` suy ra rằng instance này từng được khai báo bằng `Box<Integer>` ở source: đối tượng nhìn chung chỉ biết runtime class `Box`, còn type arguments của biến/biểu thức không được lưu riêng cho từng instance.

Có những trường hợp runtime vẫn biết generic information vì **khai báo** được ghi metadata, ví dụ `Child extends Parent<String>`. Đây là thông tin của lớp `Child`, không phải bằng chứng rằng JVM giữ parameterized type của tất cả object `Parent<String>`.

## 7. Bridge method: vì sao sau erasure lại có thêm một method?

Đây là ví dụ của cơ chế giữ nguyên đa hình giữa kiểu nguồn và JVM descriptor.

Nguồn:

```java
static class Parent<T> {
    T get() {
        return null;
    }
}

static class Child extends Parent<String> {
    @Override
    String get() {
        return "child";
    }
}
```

Ở tầng nguồn, `Child.get()` override `Parent<String>.get()`, và kết quả được xem là `String`. Nhưng sau erasure:

- `Parent<T>.get()` có descriptor `()Ljava/lang/Object;`.
- Phương thức do người viết khai báo trong `Child` có descriptor `()Ljava/lang/String;`.
- Để lời gọi vào phương thức của `Parent` tiếp tục dispatch đến `Child` đúng cách, `javac` sinh thêm một phương thức trong `Child` có descriptor `()Ljava/lang/Object;`. Phương thức này gọi đến `Child.get()` trả về `String` và đưa nó về kiểu `Object`.

Với `javap -s -p -classpath out 'ErasureLab$Child'`, phần liên quan là:

```text
java.lang.String get();
  descriptor: ()Ljava/lang/String;

java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
```

Tìm thông tin flags bằng:

```bash
javap -v -p -classpath out 'ErasureLab$Child'
```

Method phụ được đánh dấu bằng **`ACC_BRIDGE`** và **`ACC_SYNTHETIC`**. Trong ví dụ, reflection gọi `isBridge()` đếm được một bridge, nên stdout có `bridge=1`. Thứ tự các method do reflection trả về không phải thứ tự đáng dựa vào; ví dụ chỉ đếm để tránh phụ thuộc thứ tự đó.

**Cần hiểu chính xác:** bridge là một phương thức thực trong class file được compiler sinh để giữ quan hệ override sau erasure (và trong các tình huống khác như covariant return). Đây không phải là “overload hợp lệ do người viết có thể khai báo cả hai method” ở mức Java source. JLS cấm nhiều khai báo gây name clash theo quy tắc erasure, dù bytecode có thể chứa những descriptor khác nhau.

## 8. Name clash: hai overload có thể đụng nhau sau erasure

Đoạn sau **cố ý không biên dịch được**, vì hai overload chỉ khác type argument:

```java
import java.util.List;

class InvalidOverloads {
    void process(List<String> names) {
    }

    void process(List<Integer> ids) {
    }
}
```

Sau erasure cả hai đều có parameter descriptor `(Ljava/util/List;)`; đều trả `void` nên method descriptor của cả hai đều là `(Ljava/util/List;)V`. Java sẽ báo lỗi name clash vì chúng không thể được phân biệt bằng kiểu tham số sau erasure.

Một cách sửa là chọn hai tên phương thức phản ánh chức năng khác nhau:

```java
import java.util.List;

class DistinctMethods {
    void processNames(List<String> names) {
    }

    void processIds(List<Integer> ids) {
    }
}
```

Bạn cũng có thể thiết kế API chung `process(List<T>)` nếu hai thao tác thực sự có cùng ngữ nghĩa. Nhưng đừng nghĩ dùng hai type argument khác nhau cho cùng một tên `List` sẽ tạo nên hai method runtime riêng.

**Phân biệt với hai overload hợp lệ sau erasure:** `process(String)` và `process(Integer)` có parameter descriptors khác nhau, nên có thể cùng tồn tại. Khi có generics phức tạp, Java còn áp dụng quy tắc *subsignature* và *override-equivalent*; chỉ việc “nhìn bằng mắt thấy khác ở source” chưa đủ để khẳng định overload hợp lệ.

## 9. Cast, heap pollution và giới hạn kiểm tra runtime

### 9.1. Không thể kiểm tra đầy đủ type argument bằng instanceof

`List<String>` không phải một kiểu reifiable. Vì thế đoạn **cố ý sai**:

```java
import java.util.List;

class InvalidCheck {
    boolean check(Object value) {
        return value instanceof List<String>;
    }
}
```

sẽ bị từ chối lúc biên dịch. Bạn có thể kiểm tra `value instanceof List<?>` (một parameterization chỉ dùng unbounded wildcard là reifiable), hoặc kiểm tra `value instanceof List` ở mức raw type. Nhưng những kiểm tra này không chứng minh các phần tử trong list đều là `String`.

### 9.2. Unchecked conversion có thể làm lỗi xuất hiện muộn

Ví dụ này là chương trình Java chạy được nhưng được viết **cố ý không an toàn** để thấy giới hạn:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    public static void main(String[] args) {
        List raw = new ArrayList<String>();
        raw.add(42);
        List<String> strings = raw;

        try {
            String first = strings.get(0);
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

```bash
javac --release 17 -Xlint:unchecked HeapPollutionDemo.java
java HeapPollutionDemo
```

Stdout của chương trình:

```text
ClassCastException
```

`javac -Xlint:unchecked` có thể in chẩn đoán cảnh báo (stderr; câu chữ chi tiết tùy JDK), vì `raw.add(42)` và phép gán raw sang `List<String>` không được kiểm tra đầy đủ. Khi `strings.get(0)` được sử dụng như `String`, cast được compiler chèn có thể thất bại vì phần tử thật là `Integer`.

**Type erasure không làm `List<String>` trở thành “an toàn tuyệt đối ở runtime”.** Tính an toàn kiểu được thiết kế dựa trên kiểm tra compile-time và một số phép cast cần thiết. Raw types, unchecked operations, reflection, native/unsafe code hoặc binary không tương thích có thể phá giả định kiểu nguồn.

### 9.3. Các giới hạn liên quan

- Không tạo trực tiếp `new List<String>[10]` vì generic array creation bị hạn chế.
- Không viết `new T()` với type variable `T` chỉ vì đã biết bound; erasure không biến một tham số kiểu thành một constructor khả dụng.
- Không thể viết `List<String>.class`; có `List.class`, nhưng không có `Class` object riêng cho từng type argument của `List`.
- Một số khai báo dùng wildcard hoặc kiểu mảng vẫn là reifiable theo JLS `4.7; không nên kết luận quá mức rằng “mọi generic type đều không kiểm tra được ở runtime”.
- Java reflection có thể thấy **kiểu generic của khai báo** từ `Signature` attribute; đó là khả năng khác với việc kiểm tra type argument của từng instance.

## 10. Mối quan hệ với kiểm tra overload, binary API và linkage

### 10.1. Overload được chọn ở compile time

Với mã nguồn `List<String> names`, `javac` dùng kiểu parameterized đầy đủ để phát hiện thao tác không an toàn. Khi có nhiều overload, compiler áp dụng quy tắc kiểm tra ứng viên và phương thức cụ thể nhất theo JLS; không đơn giản “chọn dựa vào chuỗi JVM descriptor”.

Sau khi được biên dịch, một lời gọi có symbolic reference đến method với tên và descriptor tương ứng trong class file. Nếu sau này thay đổi binary API mà không biên dịch lại client, chương trình có thể gặp lỗi linkage, chẳng hạn `NoSuchMethodError` khi method với descriptor được client kỳ vọng không còn tồn tại.

### 10.2. Thay type arguments không nhất thiết thay descriptor

Ví dụ thay khai báo `void read(List<String> values)` thành `void read(List<Integer> values)` thì **parameter descriptor vẫn là `Ljava/util/List;`**, nhưng các quy tắc kiểu nguồn và generic `Signature` attribute có thể khác. Vì thế chỉ so sánh descriptor chưa đủ để xác nhận API generic của thư viện giữ nguyên.

Ngược lại, thay bound của type variable có thể đổi erasure và descriptor. Ví dụ:

```java
class Before<T> {
    T get() {
        return null;
    }
}

class After<T extends Number> {
    T get() {
        return null;
    }
}
```

`Before.get()` trả `Object` ở descriptor; `After.get()` trả `Number`. Đây là **hai lớp minh họa khác nhau**; nếu thay đổi bound của cùng một API đã phát hành, signature thực thi có thể đổi, nên cần kiểm tra tương thích binary. Đừng kết luận rằng sửa generic bound luôn chỉ tác động compile-time.

### 10.3. JVM descriptor và generic Signature không có vai trò bằng nhau

- JVM dùng **descriptor** trong việc mô tả kiểu parameter/return của thành viên, verification, liên kết symbolic references và thực thi invocation.
- Generic **`Signature` attribute** chứa metadata hỗ trợ khai báo generic. Compiler/reflection có thể dùng thông tin đó, nhưng nó không tạo ra một tập class runtime khác nhau cho `List<String>` và `List<Integer>`.
- Các bridge methods có descriptor riêng để duy trì dispatch khi kiểu nguồn và kiểu sau erasure có thể khiến phương thức bị ánh xạ khác nhau.

Do đó khi debug `NoSuchMethodError` hoặc khác biệt ABI, hãy xem **descriptor** trước; khi debug một thư viện bị sai generic declaration, hãy xem thêm **Signature** và source API.

## 11. Quy trình điều tra bằng javap

Khi gặp một trường hợp “type trong source không giống cái hiện trong bytecode”, làm theo thứ tự:

1. **Ghi khai báo nguồn:** type parameters, bound, wildcard, return type và parameter types; xác định overload/override.
2. **Áp dụng JLS `4.6:** thay mỗi type variable bằng erasure của bound đầu tiên, erasure các parameterized types, áp dụng vào arrays.
3. **Chuyển sang descriptor grammar:** primitives thành ký tự đơn, object thành `L...;`, array có tiền tố `[`, method có `(...)return`.
4. **Biên dịch bằng toolchain cố định:** ví dụ `javac --release 17 -d out ErasureLab.java`.
5. **Quan sát `javap -s -p`:** đọc descriptors của fields/constructors/methods, gồm các thành viên không public.
6. **Quan sát `javap -v -p`:** đọc `Signature` attribute, flags `ACC_BRIDGE`/`ACC_SYNTHETIC` nếu có.
7. **Quan sát `javap -c -p`:** tìm cast và lời gọi do compiler tạo; không suy diễn rằng compiler khác phải sinh cùng instruction offset.
8. **Đối chiếu behavior và API:** chạy chương trình, kiểm tra reflection và thử compile client; ghi rõ đâu là cam kết của JLS/JVMS và đâu là hình thức code generation của bản `javac` cụ thể.

Bảng tham chiếu nhanh:

| Quan sát | Công cụ/nguồn |
| --- | --- |
| Java source `List<String>` có hợp lệ không? | JLS: generic types, assignment, method invocation |
| Type variable `T` erasure về kiểu nào? | JLS `4.6, kiểm tra bound đầu tiên |
| Method JVM tham số/return gì? | `javap -s -p`, JVMS `4.3.3` |
| Generic metadata còn gì? | `javap -v -p`, `Signature` attribute trong JVMS `4.7.9` |
| Có bridge compiler sinh không? | `javap -v -p` flags; reflection `Method.isBridge()` |
| Vì sao xuất hiện `checkcast`? | `javap -c -p` và quy tắc conversion/typing của JLS |
| Runtime có biết `List<String>` của từng object không? | Reifiable types (JLS `4.7) và giới hạn erasure |

## 12. Các ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Generic biến mất hoàn toàn khỏi file class.” | Descriptor đã erasure nhưng `Signature` attribute có thể lưu generic declarations. |
| “`List<String>` và `List<Integer>` sẽ có JVM class khác nhau.” | Chúng cùng dùng runtime class `List`/implementation; type arguments không tạo class riêng. |
| “`TT;` là field descriptor cho type variable `T`.” | `TT;` thuộc generic signature grammar; descriptor dùng erasure của bound. |
| “Erasure luôn thay `T` bằng `Object`.” | Chỉ đúng với type variable không có bound tường minh; `T extends Number` thành `Number`. |
| “Java method signature luôn bao gồm return type vì JVM descriptor có return type.” | Hai thuật ngữ ở hai tầng khác nhau; overload Java không phân biệt chỉ theo return type. |
| “Bridge là method do lập trình viên phải viết thủ công.” | `javac` sinh bridge khi cần giữ override/dispatch sau các biến đổi phù hợp. |
| “Reflection không đọc được generic nào.” | Reflection có thể đọc `Signature` của khai báo; không tái tạo type arguments đã bị xóa của mọi instance. |
| “Một cast trong bytecode nghĩa là source chứa ép kiểu tường minh.” | Compiler có thể chèn `checkcast` do erasure để đáp ứng kiểu của expression. |
| “Generic type cho phép `instanceof List<String>`.” | Parameterized type này không reifiable, kiểm tra như vậy không hợp lệ. |
| “Hai source APIs có cùng descriptor thì generic API giống hệt.” | Type arguments/bounds trong `Signature` và quy tắc kiểu nguồn vẫn có thể khác nhau. |

## 13. Bài tập tự kiểm tra

**Bài 1.** Với khai báo `class Store<T extends CharSequence> { T read(); }`, descriptor của `read()` là gì?

**Đáp án:** `()Ljava/lang/CharSequence;`. Erasure của `T` là bound đầu tiên `CharSequence`, không phải `Object`.

**Bài 2.** Hai method `save(List<String>)` và `save(List<Integer>)` có thể overload trong cùng class không?

**Đáp án:** Không. Hai parameter types đều erasure thành `List`; hai method có cùng tên và erasure của signature nên xảy ra name clash.

**Bài 3.** Source `Map<String, List<Integer>> lookup()` có return descriptor là gì?

**Đáp án:** `()Ljava/util/Map;`. Generic signature có thể giữ phần khai báo `String` và `List<Integer>`; descriptor chỉ giữ raw `Map`.

**Bài 4.** `T extends Runnable & AutoCloseable` erasure thành gì?

**Đáp án:** `Runnable` vì đó là bound đầu tiên; field descriptor tương ứng là `Ljava/lang/Runnable;`. Vẫn có hai bound ở mức nguồn.

**Bài 5.** Vì sao `Child extends Parent<String>` có thể có hai methods `get()` trong class file, một trả `String` và một trả `Object`?

**Đáp án:** Compiler có thể sinh bridge `get():Object` (đánh dấu `ACC_BRIDGE`, `ACC_SYNTHETIC`) để duy trì polymorphic dispatch tới method `get():String` sau erasure.

**Bài 6.** `javap -s` chỉ thấy `List`. Điều đó chứng minh file `.class` hoàn toàn không ghi `String` của `List<String>`?

**Đáp án:** Không. Cần đọc `Signature` attribute bằng `javap -v`; descriptor và generic signature lưu hai loại thông tin khác nhau.

**Bài 7.** Vì sao `List<String> strings = rawList; String s = strings.get(0);` có thể ném `ClassCastException`?

**Đáp án:** Một unchecked conversion từ raw list có thể đưa phần tử sai kiểu vào collection; đọc kết quả như `String` khiến cast do compiler chèn thất bại nếu object không phải `String`.

## 14. Tài liệu chuẩn

- **JLS Java SE 21 `4.6 — Type Erasure:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6 — quy tắc erasure của parameterized types, type variables, arrays và method signatures.
- **JLS Java SE 21 `4.7 — Reifiable Types:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7 — kiểu có thể được nhận diện đầy đủ ở runtime.
- **JVMS Java SE 21 `4.3.2, `4.3.3:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3 — field và method descriptors.
- **JVMS Java SE 21 `4.7.9 — The Signature Attribute:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9 — generic signatures lưu trong class file.
- **JDK 21 javap tool reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html — sử dụng `-s`, `-p`, `-v` và `-c` để khảo sát artifact.

**Điểm cần nhớ:** đọc một method Java generic đòi hỏi tách **kiểu nguồn được JLS kiểm tra**, **kiểu sau erasure được JVM biểu diễn bằng descriptor**, và **metadata generic bổ sung trong Signature attribute**. Khi ba tầng được phân biệt rõ, bạn sẽ hiểu được vì sao compiler chèn cast, vì sao sinh bridge method và vì sao cùng một descriptor vẫn có thể tương ứng với các khai báo generic khác nhau.