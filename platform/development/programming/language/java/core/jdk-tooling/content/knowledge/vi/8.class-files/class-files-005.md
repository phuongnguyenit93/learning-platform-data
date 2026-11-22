# Field và method trong Java class file

Sau khi biên dịch, `javac` lưu thông tin về lớp Java trong tệp `.class`. Bên cạnh bytecode của các phương thức, class file còn mô tả **field (trường)**, **method (phương thức)**, kiểu dữ liệu, quyền truy cập, generic signature và nhiều thuộc tính khác.

Hiểu cách field và method được biểu diễn giúp đọc kết quả `javap -verbose`, điều tra lỗi liên kết lớp, kiểm tra API của thư viện và hiểu vì sao mã nguồn Java đôi khi không xuất hiện giống hệt trong class file.

## 1. Field và method là gì?

Trong mã nguồn Java:

- **Field** là biến được khai báo trực tiếp bên trong lớp hoặc interface. Field có thể là biến instance hoặc biến static.
- **Method** là một đơn vị hành vi được khai báo trong lớp hoặc interface. Method có thể nhận tham số, trả về giá trị hoặc không trả về giá trị.
- **Constructor** là thành phần khởi tạo đối tượng. Trong class file, constructor được biểu diễn như một method đặc biệt có tên `<init>`.
- **Class initializer** là phần khởi tạo static. Nếu cần mã để thực hiện static initializer, compiler tạo method đặc biệt tên `<clinit>`.

Ví dụ:

```java
public class Account {
    private String owner;        // field instance
    private static int total;    // field static

    public Account(String owner) { // constructor
        this.owner = owner;
        total++;
    }

    public String getOwner() {   // method
        return owner;
    }
}
```

Field lưu trạng thái của lớp hoặc đối tượng. Method mô tả thao tác có thể thực hiện trên trạng thái đó.

## 2. Class file lưu field và method ở đâu?

Theo định dạng class file của JVM, sau phần header và constant pool, class file có các phần chính:

1. Access flags, tên lớp hiện tại và tên lớp cha.
2. Danh sách interface mà lớp triển khai.
3. Danh sách field.
4. Danh sách method.
5. Danh sách attribute ở cấp lớp.

Hai cấu trúc mô tả field và method có dạng tương tự:

```text
field_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}

method_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
```

Các trường `name_index` và `descriptor_index` là chỉ số tham chiếu đến mục trong constant pool, không phải chuỗi tên hoặc kiểu được lưu trực tiếp tại vị trí đó.

- `access_flags`: các cờ mô tả quyền truy cập và đặc tính của field/method.
- `name_index`: tên field hoặc tên method.
- `descriptor_index`: mô tả kiểu field hoặc chữ ký kiểu của method theo định dạng JVM.
- `attributes_count`: số thuộc tính bổ sung.
- `attributes`: các thông tin bổ sung như hằng số, generic signature, bytecode, exception hoặc annotation.

Class file có `fields_count` và `methods_count` để cho biết số lượng phần tử trong từng danh sách.

## 3. Descriptor là gì?

**Descriptor** là chuỗi ký hiệu chuẩn mà JVM dùng để mô tả kiểu của field và tham số/giá trị trả về của method. Descriptor khác với tên kiểu Java hiển thị trong mã nguồn.

### Descriptor của field

Một số ký hiệu kiểu cơ bản:

| Ký hiệu | Kiểu Java |
| --- | --- |
| `B` | `byte` |
| `C` | `char` |
| `D` | `double` |
| `F` | `float` |
| `I` | `int` |
| `J` | `long` |
| `S` | `short` |
| `Z` | `boolean` |
| `L...;` | Kiểu tham chiếu |
| `[...` | Kiểu mảng |

Ví dụ:

| Khai báo Java | Field descriptor |
| --- | --- |
| `int count;` | `I` |
| `boolean active;` | `Z` |
| `long id;` | `J` |
| `String name;` | `Ljava/lang/String;` |
| `int[] values;` | `[I` |
| `String[][] names;` | `[[Ljava/lang/String;` |

Tên lớp trong descriptor dùng dấu gạch chéo `/` để phân cách package và kết thúc bằng dấu chấm phẩy. Ví dụ `java.lang.String` được biểu diễn là `Ljava/lang/String;`.

### Descriptor của method

Descriptor method có cấu trúc:

```text
(kiểu_tham_số_1 kiểu_tham_số_2 ...)kiểu_trả_về
```

Phần tham số nằm giữa cặp ngoặc đơn. Kiểu trả về đứng sau dấu ngoặc đóng. Nếu method trả về `void`, ký hiệu là `V`.

Ví dụ:

| Khai báo Java | Method descriptor |
| --- | --- |
| `void run()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `String find(int id)` | `(I)Ljava/lang/String;` |
| `boolean matches(String text, int mode)` | `(Ljava/lang/String;I)Z` |
| `void setNames(String[] names)` | `([Ljava/lang/String;)V` |

Descriptor không bao gồm tên tham số. Vì vậy, hai method overload có cùng tên nhưng khác kiểu tham số sẽ có descriptor khác nhau.

Ví dụ:

```java
void print(int value);
void print(String value);
```

Hai descriptor lần lượt là `(I)V` và `(Ljava/lang/String;)V`.

## 4. Access flags của field

Field có các cờ mô tả quyền truy cập và đặc tính. Một số cờ thường gặp:

| Cờ | Ý nghĩa |
| --- | --- |
| `ACC_PUBLIC` | Field có quyền truy cập public |
| `ACC_PRIVATE` | Field chỉ truy cập trong phạm vi lớp khai báo theo quy tắc Java |
| `ACC_PROTECTED` | Field có quyền truy cập protected |
| `ACC_STATIC` | Field thuộc lớp thay vì từng đối tượng |
| `ACC_FINAL` | Field chỉ được gán một lần theo quy tắc của final |
| `ACC_VOLATILE` | Field có ngữ nghĩa volatile trong mô hình bộ nhớ Java |
| `ACC_TRANSIENT` | Field được đánh dấu transient đối với cơ chế serialization mặc định |
| `ACC_SYNTHETIC` | Thành viên được compiler sinh ra, không khai báo trực tiếp trong mã nguồn |
| `ACC_ENUM` | Field biểu diễn một hằng số enum |

Ví dụ:

```java
public static final int MAX_RETRIES = 3;
private volatile boolean running;
private transient String cachedToken;
```

Các field trên có thể mang những tổ hợp cờ tương ứng như `ACC_PUBLIC`, `ACC_STATIC`, `ACC_FINAL`, `ACC_PRIVATE`, `ACC_VOLATILE` hoặc `ACC_TRANSIENT`.

Access flags trong class file là biểu diễn cấp JVM. Quy tắc truy cập thực tế còn liên quan đến package, class, subclass, module và các quy tắc của ngôn ngữ Java.

## 5. Access flags của method

Method cũng có các cờ truy cập và cờ mô tả cách thực thi.

| Cờ | Ý nghĩa |
| --- | --- |
| `ACC_PUBLIC` | Method public |
| `ACC_PRIVATE` | Method private |
| `ACC_PROTECTED` | Method protected |
| `ACC_STATIC` | Method static |
| `ACC_FINAL` | Method không thể bị override theo quy tắc Java |
| `ACC_SYNCHRONIZED` | Method có cơ chế đồng bộ hóa khi gọi |
| `ACC_BRIDGE` | Method bridge do compiler sinh ra để hỗ trợ generic/covariant return |
| `ACC_VARARGS` | Method khai báo tham số dạng varargs |
| `ACC_NATIVE` | Method được triển khai bằng mã native |
| `ACC_ABSTRACT` | Method trừu tượng, không có phần thân bytecode |
| `ACC_SYNTHETIC` | Method được compiler sinh ra |

Ví dụ:

```java
public static void main(String[] args) {
    // ...
}

public synchronized void update() {
    // ...
}

public abstract void execute();
```

Một method `abstract` hoặc `native` không có phần thân bytecode thông thường, vì vậy không có thuộc tính `Code` như một method Java có phần thân.

Không nên nhầm `ACC_BRIDGE` với một method được lập trình viên viết trực tiếp. Compiler có thể tạo bridge method để duy trì quy tắc dispatch và tương thích kiểu khi sử dụng generic hoặc kiểu trả về covariant.

## 6. Các attribute quan trọng của field

Sau các chỉ số tên và descriptor, field có thể mang nhiều attribute.

### ConstantValue

`ConstantValue` lưu giá trị hằng số cho một số field static final có giá trị hằng tại thời điểm biên dịch, chẳng hạn primitive hoặc String constant variable.

Ví dụ:

```java
public static final int LIMIT = 100;
public static final String LABEL = "JAVA";
```

Khi xem bằng `javap -verbose`, có thể thấy thông tin tương tự:

```text
public static final int LIMIT;
  descriptor: I
  flags: ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 100
```

Không phải mọi field `static final` đều có `ConstantValue`. Nếu giá trị cần được tính toán trong lúc chạy hoặc khởi tạo bằng biểu thức không phải constant expression, compiler có thể tạo mã trong class initializer thay vì dùng attribute này.

Một lưu ý quan trọng: giá trị hằng primitive/String public có thể được compiler của mã sử dụng inline vào class phụ thuộc. Khi thay đổi hằng số trong thư viện, đôi khi cần biên dịch lại các client để chúng nhận giá trị mới.

### Signature

Attribute `Signature` lưu thông tin generic signature mà descriptor thông thường không thể hiện đầy đủ.

Ví dụ:

```java
private List<String> names;
```

Descriptor field là:

```text
Ljava/util/List;
```

Thông tin generic có thể được lưu trong Signature attribute:

```text
Ljava/util/List<Ljava/lang/String;>;
```

JVM liên kết field theo descriptor đã xóa generic (type erasure). Generic Signature giữ lại thông tin cho compiler, reflection và công cụ phân tích.

### RuntimeVisibleAnnotations và RuntimeInvisibleAnnotations

Annotation trên field có thể được lưu trong các attribute annotation:

- `RuntimeVisibleAnnotations`: annotation có thể được truy cập khi chạy bằng reflection nếu retention phù hợp.
- `RuntimeInvisibleAnnotations`: annotation được lưu trong class file nhưng không được cung cấp như annotation runtime-visible qua reflection thông thường.

Ví dụ:

```java
@Deprecated
private String oldName;
```

Tùy annotation và chính sách retention, metadata annotation tương ứng được lưu trong class file.

## 7. Các attribute quan trọng của method

Method có thể có các attribute mô tả phần thân, ngoại lệ, generic, tham số và annotation.

### Code

Với method có phần thân bytecode, attribute `Code` chứa:

- `max_stack`: độ sâu tối đa của operand stack cần thiết.
- `max_locals`: số slot local variable cần thiết.
- `code_length` và `code[]`: độ dài và chuỗi bytecode.
- `exception_table`: thông tin xử lý exception trong method.
- Các attribute lồng bên trong, ví dụ `LineNumberTable`, `LocalVariableTable` và `StackMapTable`.

Method abstract và native không có attribute `Code` thông thường vì chúng không có phần thân bytecode trong class file.

### Exceptions

Attribute `Exceptions` liệt kê các checked exception được khai báo trong mệnh đề `throws` của method.

Ví dụ:

```java
public void load() throws java.io.IOException {
    // ...
}
```

Thông tin `throws IOException` có thể được hiển thị bởi `javap` và lưu trong Exceptions attribute. Attribute này phục vụ thông tin khai báo; cơ chế xử lý exception khi chạy được biểu diễn riêng trong bytecode và exception table của Code attribute.

### Signature và MethodParameters

- `Signature` lưu generic signature của method khi cần.
- `MethodParameters` có thể lưu tên tham số và các cờ liên quan khi biên dịch với `-parameters`.

Ví dụ:

```java
public <T> T first(List<T> values) {
    return values.get(0);
}
```

Descriptor runtime của method sau type erasure là:

```text
(Ljava/util/List;)Ljava/lang/Object;
```

Generic Signature giữ thông tin gần với khai báo nguồn:

```text
<T:Ljava/lang/Object;>(Ljava/util/List<TT;>;)TT;
```

Descriptor được dùng cho liên kết ở cấp JVM; Signature giữ metadata generic cho công cụ và reflection.

### Annotation và AnnotationDefault

Annotation có thể xuất hiện trên method hoặc tham số. Với annotation method của một annotation type, attribute `AnnotationDefault` có thể lưu giá trị mặc định của phần tử annotation.

Ví dụ:

```java
public @interface Role {
    String value() default "USER";
}
```

Giá trị mặc định `USER` được biểu diễn trong class file của annotation type bằng attribute phù hợp.

## 8. Constructor và class initializer trong class file

Constructor và static initializer có tên đặc biệt trong class file:

- `<init>`: constructor instance. Descriptor kết thúc bằng `V` vì constructor không trả về giá trị.
- `<clinit>`: method khởi tạo class static, có descriptor `()V`.

Ví dụ:

```java
public class Config {
    private static final int DEFAULT_PORT = 8080;
    private static int currentPort;

    static {
        currentPort = DEFAULT_PORT + 1;
    }

    public Config() {
    }
}
```

Compiler tạo constructor `<init>`. Vì có static initialization block, compiler cũng tạo `<clinit>` để thực hiện mã khởi tạo static.

Không phải lớp nào cũng cần `<clinit>`. Nếu không có thao tác khởi tạo static cần thực thi, method này có thể không xuất hiện. Một hằng số compile-time như `static final int DEFAULT_PORT = 8080` thường được biểu diễn bằng ConstantValue và tự nó không nhất thiết cần tạo `<clinit>`.

## 9. Ví dụ hoàn chỉnh: kiểm tra field và method bằng javap

Tạo tệp **`MemberDemo.java`**:

```java
import java.util.List;

public class MemberDemo<T> {
    public static final int MAX = 10;
    private static final String LABEL = "demo";

    private int count;
    private T value;

    public MemberDemo(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }

    public void setCount(int count) {
        this.count = count;
    }

    public boolean isPositive(int number) {
        return number > 0;
    }

    public static String format(String prefix, int number) {
        return prefix + number;
    }

    public List<String> names() {
        return List.of(LABEL);
    }

    public static void main(String[] args) {
        MemberDemo<String> demo = new MemberDemo<>("Java");
        System.out.println(demo.getValue());
        System.out.println(demo.isPositive(5));
    }
}
```

Biên dịch với thông tin debug và tên tham số:

```bash
javac -g -parameters -d out MemberDemo.java
```

Xem các thành viên kể cả private:

```bash
javap -classpath out -p MemberDemo
```

Xem descriptor của field và method:

```bash
javap -classpath out -p -s MemberDemo
```

Xem toàn bộ metadata và attribute:

```bash
javap -classpath out -p -s -v MemberDemo
```

Trong kết quả, có thể nhận diện:

- `MAX`: field static final int, descriptor `I`, có ConstantValue.
- `LABEL`: field static final String, descriptor `Ljava/lang/String;`.
- `count`: field instance int, descriptor `I`.
- `value`: field generic `T`, descriptor đã xóa generic là `Ljava/lang/Object;`, kèm Signature nếu được giữ.
- `<init>`: constructor nhận một Object sau type erasure.
- `getValue()`: descriptor trả về Object, Signature thể hiện kiểu generic T.
- `format(String, int)`: descriptor `(Ljava/lang/String;I)Ljava/lang/String;`.
- `main(String[])`: descriptor `([Ljava/lang/String;)V`.

Chạy chương trình:

```bash
java -cp out MemberDemo
```

Kết quả:

```text
Java
true
```

Lưu ý: output chi tiết của `javap` có thể khác về thứ tự constant pool index, offset bytecode và cách trình bày giữa các bản JDK. Hãy tập trung vào descriptor, access flags và ý nghĩa attribute thay vì phụ thuộc vào số index cụ thể.

## 10. Đọc output javap theo thứ tự nào?

Khi kiểm tra một class file, có thể đọc theo trình tự:

1. **Tên lớp và superclass:** xác nhận đúng class đang phân tích.
2. **Field:** xem tên, descriptor, access flags và ConstantValue.
3. **Method:** xem tên, descriptor, quyền truy cập và các thuộc tính khai báo.
4. **Code:** với method có phần thân, xem bytecode, max stack, local slots và exception table.
5. **Signature:** kiểm tra generic type có được giữ trong metadata hay đã bị type erasure ở descriptor.
6. **Exceptions và annotations:** kiểm tra khai báo throws và metadata annotation.
7. **Debug attributes:** kiểm tra LineNumberTable, LocalVariableTable và MethodParameters nếu cần điều tra.

Các lệnh hữu ích:

| Mục đích | Lệnh |
| --- | --- |
| Xem khai báo public | `javap -classpath out MemberDemo` |
| Xem cả private field/method | `javap -classpath out -p MemberDemo` |
| Xem descriptor | `javap -classpath out -p -s MemberDemo` |
| Xem bytecode method | `javap -classpath out -c MemberDemo` |
| Xem metadata chi tiết | `javap -classpath out -v MemberDemo` |
| Xem constant field | `javap -classpath out -constants MemberDemo` |
| Xem thông tin debug | `javap -classpath out -l MemberDemo` |

Nếu lớp nằm trong package, dùng tên đầy đủ, ví dụ `com.example.MemberDemo`, và classpath phải trỏ đến thư mục gốc chứa package `com`.

## 11. Field và method có thể khác mã nguồn như thế nào?

Class file là kết quả biên dịch, vì vậy không phải mọi thành viên trong đó đều tương ứng một-một với dòng khai báo trong mã nguồn.

Một số tình huống thường gặp:

- Compiler tạo bridge method để hỗ trợ generic và covariant return.
- Compiler tạo synthetic field hoặc method để hỗ trợ một số cấu trúc ngôn ngữ.
- Constructor mặc định có thể được compiler tạo nếu lớp không khai báo constructor.
- Static initializer được gom vào `<clinit>`.
- Generic type bị type erasure trong descriptor, trong khi Signature có thể lưu thông tin generic.
- Tên tham số và biến cục bộ có thể không có trong class file nếu không biên dịch kèm metadata tương ứng.

Vì vậy, khi kiểm tra thư viện hoặc điều tra hành vi runtime, hãy xem class file là biểu diễn ở cấp JVM, không phải bản sao nguyên văn của mã nguồn Java.

## 12. Lỗi thường gặp khi phân tích field và method

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy field private | `javap` mặc định chỉ hiển thị thành viên public/protected theo chế độ xem | Dùng `javap -p` |
| Không hiểu descriptor | Nhầm ký hiệu JVM với kiểu Java | Tách descriptor thành tham số, kiểu trả về và kiểu tham chiếu |
| Generic T hiển thị thành Object | Descriptor phản ánh type erasure | Xem thêm Signature attribute bằng `javap -v` |
| Không thấy bytecode của method | Method abstract/native hoặc chưa dùng `-c` | Kiểm tra cờ method và chạy `javap -c` |
| Không thấy ConstantValue | Field không phải constant variable phù hợp hoặc được khởi tạo lúc chạy | Xem `<clinit>` và bytecode khởi tạo |
| Không thấy tên tham số | Class không được biên dịch với `-parameters` | Biên dịch lại với `javac -parameters` |
| Không thấy tên biến cục bộ/số dòng | Thiếu debug attributes | Biên dịch với `javac -g` |
| Thấy method không có trong mã nguồn | Compiler sinh bridge/synthetic method hoặc method được kế thừa/biểu diễn đặc biệt | Kiểm tra access flags, `ACC_BRIDGE` và `ACC_SYNTHETIC` |

## 13. Ghi nhớ

- Class file có danh sách field và method riêng; mỗi thành viên được mô tả bằng access flags, tên, descriptor và attributes.
- Field descriptor mô tả kiểu dữ liệu; method descriptor mô tả kiểu tham số và kiểu trả về.
- Generic type thường bị type erasure trong descriptor; Signature có thể giữ thông tin generic.
- `ConstantValue` lưu một số giá trị hằng static final; không phải mọi field final đều có attribute này.
- `Code` chứa bytecode của method có phần thân; abstract và native method không có Code attribute thông thường.
- `<init>` là constructor, còn `<clinit>` là class initializer.
- Dùng `javap -p -s -v` để kiểm tra thành viên private, descriptor và metadata chi tiết.

Khi hiểu cấu trúc field và method trong class file, bạn có thể đọc chính xác API ở cấp JVM, nhận diện generic erasure, phân tích bytecode và chẩn đoán các vấn đề liên quan đến liên kết lớp hoặc tương thích thư viện.
