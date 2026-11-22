# Hạ cấu trúc ngôn ngữ và sinh tệp class trong Java

Một chương trình Java không được đưa nguyên văn từng cấu trúc mã nguồn vào JVM. Trong quá trình biên dịch, trình biên dịch phải **hiểu ý nghĩa** của nguồn, biểu diễn nó bằng các cấu trúc nội bộ, chuyển một số tính năng ngôn ngữ cấp cao thành những dạng có thể biểu diễn bằng bytecode JVM (**lowering / desugaring**), rồi **sinh một hoặc nhiều tệp `.class`**. Bài học này giải thích các bước và hệ quả quan sát được khi dùng `javac` và `javap` trên Java 17+.

## 1. Vị trí của lowering trong quy trình biên dịch

Luồng khái niệm:

~~~text
Các tệp nguồn .java
        |
        v
Parse: token, cú pháp, cây biểu diễn mã nguồn (AST)
        |
        v
Enter / resolve / type-check / flow analysis
        |  Xác định ký hiệu, kiểu, overload, quyền truy cập,
        |  definite assignment, checked exceptions...
        v
Lowering / desugaring và các biến đổi phục vụ sinh mã
        |  Biểu diễn cấu trúc cấp cao bằng operations phù hợp JVM
        |  (có thể phát sinh nhánh, method bridge, method phụ...)
        v
Sinh bytecode, constant pool, thuộc tính và metadata
        |
        v
Một hoặc nhiều tệp .class
        |
        v
Class loader + JVM: loading, linking, initialization, execution
~~~

Sơ đồ mang tính **khái niệm**. Trong trình biên dịch `javac`, nhiều pass riêng thực hiện phân giải kiểu, xóa kiểu generic, chuyển đổi cú pháp, xử lý lambda và sinh mã; tên pass và thứ tự chi tiết là **nội bộ triển khai**, không phải API hay hợp đồng của Java Language Specification (JLS).

Cần phân biệt ba việc:

- **Phân tích ngữ nghĩa:** xác nhận `x + y` hợp lệ, chọn method overload, kiểm tra `return`/`throw`, kiểm tra biến được gán trước khi đọc. Nếu mã nguồn sai, compiler có thể dừng trước khi sinh class hoàn chỉnh.
- **Lowering:** chuyển biểu diễn cấp cao sang những operations thấp hơn, ví dụ `for-each` trên `Iterable` thành thao tác iterator, hoặc `try-with-resources` thành logic đóng tài nguyên an toàn.
- **Code generation:** mã hóa operations cuối cùng thành instruction JVM và metadata của `.class`. Bytecode thường dùng operand stack và local variable slots, chứ không phải cú pháp Java gốc.

Lowering **không đồng nghĩa tối ưu hóa mọi thứ**. Một số cách sinh mã phụ thuộc phiên bản `javac`, cấu hình mục tiêu và tính năng JVM hỗ trợ. JIT của JVM có thể tối ưu tiếp **khi chương trình chạy**; đó là giai đoạn khác với Java source compilation.

## 2. Vì sao Java cần hạ cấu trúc ngôn ngữ?

Ngôn ngữ nguồn cung cấp những tiện ích giúp viết code ngắn, dễ hiểu và an toàn hơn. Nhưng JVM hoạt động trên tập instruction và định dạng class file được định nghĩa riêng. Compiler phải bảo toàn **ngữ nghĩa quan sát được**, kể cả thứ tự đánh giá, exception, quyền truy cập, kiểu dữ liệu và hành vi khi có side effect.

Ví dụ, chương trình:

~~~java
// Mã minh họa bên trong một method
int total = 0;
for (int value : new int[] {2, 4, 6}) {
    total += value;
}
~~~

không yêu cầu JVM có instruction tên là “enhanced-for”. Compiler có thể biểu diễn thao tác tương đương như lặp theo chỉ số trên array. Bản viết lại **mang tính mô hình**:

~~~java
int[] array = new int[] {2, 4, 6};
int total = 0;
for (int index = 0; index < array.length; index++) {
    int value = array[index];
    total += value;
}
~~~

Điểm quan trọng: biểu thức tạo array phải được đánh giá đúng số lần, với thứ tự và các trường hợp lỗi phù hợp. Đây không phải cam kết rằng `javac` bắt buộc sinh y nguyên tên biến hoặc cấu trúc bytecode trên. Compiler thường dùng local variable slots, branch instructions và array loads thay cho cú pháp `for-each`.

Khi tìm hiểu bytecode, hãy tách **ngữ nghĩa được Java bảo đảm** khỏi **một chiến lược lowering của phiên bản compiler cụ thể**.

## 3. Những cấu trúc ngôn ngữ thường được hạ xuống bytecode

### 3.1. Enhanced `for` với array và `Iterable`

Với array, compiler có thể tổ chức vòng lặp quanh độ dài và chỉ số; bytecode liên quan đến `arraylength`, instruction load phần tử theo kiểu (`iaload`, `aaload`,...) và nhánh.

Với `Iterable<T>`, compiler dùng các thao tác tương ứng `iterator()`, `hasNext()` và `next()`. Ví dụ:

~~~java
// Mã minh họa trong method, với List<Integer> values
int sum = 0;
for (int n : values) {
    sum += n;
}
~~~

Một mô hình dễ đọc của hành vi:

~~~java
java.util.Iterator<Integer> it = values.iterator();
while (it.hasNext()) {
    int n = it.next(); // Có unboxing từ Integer thành int
    sum += n;
}
~~~

Sau xóa kiểu generic, bytecode có thể gồm cast sang `Integer` và gọi `intValue()` khi cần chuyển sang primitive `int`. Không suy ra rằng JVM “chạy generic type parameter” như một kiểu runtime được tái tạo đầy đủ.

### 3.2. Switch expression và `yield`

Java 17 hỗ trợ switch expression ổn định:

~~~java
static String label(int amount) {
    return switch (amount) {
        case 0 -> "zero";
        case 1, 2 -> "few";
        default -> "many";
    };
}
~~~

Switch expression có **giá trị kết quả**, nên compiler phải nối các nhánh thành đường thực thi tạo ra giá trị phù hợp. Trên mã bytecode có thể thấy nhánh hoặc instruction `tableswitch` / `lookupswitch` và các instruction trả về giá trị.

Trường hợp dùng block:

~~~java
static int classify(int code) {
    return switch (code) {
        case 1 -> {
            int value = code * 10;
            yield value;
        }
        default -> -1;
    };
}
~~~

`yield` chuyển giá trị cho switch expression, **không phải** method `Thread.yield()` và không phải method-level `return`. Cách tổ chức nhánh cụ thể là chi tiết sinh mã; điều cần giữ là kết quả, thứ tự đánh giá và xử lý các trường hợp hợp lệ.

### 3.3. `try-with-resources` và ngoại lệ bị suppressed

~~~java
try (Resource resource = openResource()) {
    use(resource);
}
~~~

là cú pháp nguồn cấp cao. Compiler sinh logic tương đương `try`/`finally` để đóng tài nguyên theo thứ tự quy định, kể cả khi block ném exception. Nếu block ném exception chính và `close()` cũng ném exception, exception từ `close()` có thể được gắn vào exception chính thông qua `addSuppressed`, không được tùy tiện thay thế exception chính.

Đây là ví dụ **Java 17+ độc lập, chạy được**, không dùng API ngoài JDK:

~~~java
// File: SuppressedDemo.java
public final class SuppressedDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("body");
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
            System.out.println(error.getSuppressed().length);
            System.out.println(error.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 SuppressedDemo.java
java SuppressedDemo
~~~

Stdout chính xác:

~~~text
body
1
close
~~~

`IllegalArgumentException("body")` là exception chính. `Resource.close()` ném exception thứ hai; compiler-generated resource cleanup gắn nó làm suppressed exception. Nếu tự viết một `finally { resource.close(); }` ngây thơ, bạn có thể vô tình đánh mất exception chính. Đây là ví dụ vì sao lowering phải **giữ ngữ nghĩa** chứ không chỉ thay cú pháp.

### 3.4. Autoboxing và unboxing

Mã nguồn:

~~~java
// Mã minh họa bên trong method
Integer boxed = 7;
int unboxed = boxed;
~~~

có thể trở thành những thao tác tương đương gọi `Integer.valueOf(7)` và `boxed.intValue()`. Không có một kiểu “int hoặc Integer đều như nhau” trong class file. Unboxing một tham chiếu null vẫn gây `NullPointerException`.

### 3.5. String concatenation

~~~java
String message = "id=" + id + ", ok=" + ok;
~~~

với giá trị động có thể được `javac` của các JDK hiện đại biên dịch bằng `invokedynamic` kết hợp `StringConcatFactory`. Trên các mục tiêu/phiên bản khác, cách sinh mã có thể khác (chẳng hạn dùng `StringBuilder`). **Hành vi nối chuỗi do ngôn ngữ bảo đảm**; một mẫu bytecode cụ thể thì không nên coi là hợp đồng.

### 3.6. Xóa kiểu generic và bridge methods

Generic giúp kiểm tra kiểu ở mã nguồn. Khi sinh bytecode, thông tin generic thường được **erasure** thành kiểu giới hạn (*bound*) hoặc `Object` và thêm cast khi cần. Thông tin generic có thể còn trong metadata `Signature` cho tooling/reflection, nhưng JVM method descriptor vẫn dựa trên các kiểu đã erasure.

Ví dụ:

~~~java
interface Provider<T> {
    T get();
}

final class StringProvider implements Provider<String> {
    @Override
    public String get() {
        return "ready";
    }
}
~~~

Ở mức JVM, method của interface sau erasure có descriptor tương ứng `()Ljava/lang/Object;`, còn method thật của `StringProvider` trả `String`. Để bảo đảm lời gọi qua `Provider` vẫn dispatch đúng, `javac` có thể tạo **bridge method** với chữ ký erasure `Object get()`, chuyển tiếp đến `String get()`.

`Bridge` được đánh dấu bằng cờ class-file thích hợp (`ACC_BRIDGE` và thường `ACC_SYNTHETIC`). Không tự khai báo thêm `Object get()` trong source: compiler tạo cầu nối khi cần để bảo toàn overriding/polymorphism.

### 3.7. Lambda và method references

~~~java
Runnable action = () -> System.out.println("run");
action.run();
~~~

Trong `javac` của các JDK hiện đại, lambda thường được chuyển thành một call site `invokedynamic` cùng bootstrap metadata tham chiếu `LambdaMetafactory` và một method body do compiler sinh. JVM có thể tạo/cấp implementation thích hợp tại runtime.

**Không kết luận rằng mỗi lambda chắc chắn sinh một tệp `.class` riêng trong thư mục output.** Chẳng hạn *anonymous class expression* truyền thống thường tạo class file như `Outer$1.class`, còn lambda thường không tạo tệp như vậy khi biên dịch bằng `javac` hiện đại. Java chỉ yêu cầu ngữ nghĩa phù hợp; cơ chế hiện thực và tên method tổng hợp là chi tiết triển khai.

Method reference như `String::trim` cũng tạo một functional interface target và có thể dùng cơ chế lambda/metafactory tương tự. Compiler còn phải kiểm tra kiểu functional interface, capture và overload trước khi sinh mã.

### 3.8. Record và các method được tổng hợp

Java 17 hỗ trợ record:

~~~java
record Point(int x, int y) { }
~~~

Record khai báo *state description* ngắn gọn; compiler sinh/sắp xếp những phần cần thiết như các component fields private final, accessor `x()`/`y()`, canonical constructor và các method `equals`, `hashCode`, `toString` tương ứng nếu người viết không tự định nghĩa. Class sinh ra kế thừa `java.lang.Record` và có metadata `Record` trong class file.

Một bản javac hiện đại có thể dùng `invokedynamic` liên kết với `java.lang.runtime.ObjectMethods` cho các method tạo tự động. **Không mặc định** record được “dịch đúng thành một class Java văn bản” với từng dòng code như tài liệu mô phỏng; compiler tạo trực tiếp bytecode và metadata theo quy tắc record.

### 3.9. Local classes, anonymous classes và member classes

Một source file có thể tạo **nhiều tệp `.class`**:

~~~java
public final class Outer {
    static final class Nested { }

    public Runnable make() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };
    }
}
~~~

Ví dụ này thường sinh `Outer.class`, `Outer$Nested.class` và `Outer$1.class` với `javac`. Những tên có dấu `$` là **binary names** thường thấy; không dùng `Outer$1` làm tên source của một khai báo public bình thường. Các file bổ sung chứa định nghĩa lớp thật, không đơn thuần là một phần bản sao của outer class.

Từ Java 11, **nest-based access control** của JVM hỗ trợ truy cập private giữa các thành viên của cùng *nest* qua metadata `NestHost` và `NestMembers` khi phù hợp. Những compiler/runtime cũ có thể dùng synthetic accessors cho vài trường hợp. Đừng mặc định nested private access của Java 17 luôn sinh `access$000`.

### 3.10. `var`, constant folding và điều không còn ở runtime

`var` trong khai báo biến cục bộ là **suy luận kiểu tại compile time**. Nó không tạo một “dynamic var” trong class file:

~~~java
var count = 3; // Compiler suy ra int
~~~

Compiler có thể gấp những **constant expressions** theo quy tắc ngôn ngữ:

~~~java
int value = 2 * 3;
~~~

thay vì bắt JVM nhân hai số tại runtime; những chi tiết tối ưu phụ thuộc compiler và tình huống. Java vẫn phải bảo toàn các quy tắc tràn số integer, thời điểm đánh giá và side effect. Không đánh đồng suy luận kiểu của `var` với Java reflection hoặc dynamic dispatch.

## 4. Thí nghiệm tổng hợp: một nguồn thành nhiều class file

Tạo tệp **`src/LoweringDemo.java`**:

~~~java
import java.util.List;

public final class LoweringDemo {
    interface Provider<T> {
        T get();
    }

    static final class WordProvider implements Provider<String> {
        @Override
        public String get() {
            return "ready";
        }
    }

    record Point(int x, int y) { }

    static int sum(List<Integer> values) {
        int result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }

    static String label(int number) {
        return switch (number) {
            case 0 -> "zero";
            case 1, 2 -> "few";
            default -> "many";
        };
    }

    public static void main(String[] args) {
        System.out.println(sum(List.of(1, 2, 3)));
        System.out.println(label(2));

        Provider<String> provider = new WordProvider();
        System.out.println(provider.get());

        Runnable task = () -> System.out.println("lambda-run");
        task.run();

        Point point = new Point(2, 4);
        System.out.println(point.x());
    }
}
~~~

**Yêu cầu:** sử dụng một JDK 17 hoặc mới hơn; biên dịch với `--release 17` để sinh bytecode và kiểm tra API nguồn tương thích Java 17. Đứng tại thư mục gốc chứa `src`:

~~~bash
mkdir out
javac -encoding UTF-8 --release 17 -d out src/LoweringDemo.java
java -cp out LoweringDemo
~~~

Nếu `out` đã tồn tại, bỏ qua `mkdir out`. Đầu ra stdout:

~~~text
6
few
ready
lambda-run
2
~~~

**Đối chiếu từng dòng:**

1. Vòng for-each trên `List<Integer>` tính `1 + 2 + 3 = 6`; compiler kiểm tra kiểu, sinh logic iterator và unboxing khi cần.
2. `switch` expression nhận `2` và tạo chuỗi `"few"`.
3. `Provider<String>` gọi `get()` trên `WordProvider` và in `ready`; bridge method giúp dispatch tương thích descriptor sau erasure.
4. Lambda tạo một `Runnable` được thực thi khi gọi `task.run()`, không phải khi parser gặp biểu thức lambda.
5. Record component accessor `point.x()` trả về `2`.

Các tệp class dự kiến sau biên dịch thành công (có thể còn khác theo compiler):

~~~text
out/
├── LoweringDemo.class
├── LoweringDemo$Provider.class
├── LoweringDemo$WordProvider.class
└── LoweringDemo$Point.class
~~~

Bạn có thể liệt kê thư mục `out` bằng công cụ hệ điều hành. **Điều cần quan sát:** một `LoweringDemo.java` sinh nhiều tệp `.class` vì nó khai báo thêm các nested types. Lambda trong ví dụ không bắt buộc tạo một tệp `LoweringDemo$...class` riêng. Không nên khẳng định tổng số file luôn đúng như danh sách trên cho mọi compiler/phiên bản và processor.

### Đọc bytecode bằng `javap`

~~~bash
javap -classpath out -c -p LoweringDemo
javap -classpath out -v -p LoweringDemo
javap -classpath out -c -p 'LoweringDemo$WordProvider'
javap -classpath out -v -p 'LoweringDemo$Point'
~~~

Dấu nháy đơn quanh tên chứa `$` tránh shell coi `$WordProvider` là biến. Nếu chạy bằng shell khác không hiểu single quote tương tự, dùng cách escape tên lớp tương ứng.

Gợi ý quan sát mà **không phụ thuộc offset/bytecode chính xác**:

| Nơi xem | Dấu hiệu có thể thấy với `javac` Java 17 | Ý nghĩa |
| --- | --- | --- |
| Method `sum` | `Iterator`, `hasNext`, `next`, `checkcast`, `intValue` | For-each và generic/unboxing chuyển thành các thao tác JVM |
| Method `label` | Nhánh switch hoặc điều kiện, instruction trả chuỗi | Switch expression được diễn đạt bằng điều khiển luồng |
| `LoweringDemo$WordProvider` | Hai chữ ký `get`, một method có `ACC_BRIDGE`/`ACC_SYNTHETIC` | Giữ tương thích lời gọi interface sau generic erasure |
| Method `main` | `invokedynamic` cho lambda, call site gọi functional interface | Lambda không cần source class tên riêng |
| `LoweringDemo$Point` | Extends `java.lang.Record`, component fields/accessors, `Record` attribute | Metadata và method của record |
| `javap -v` | `major version: 61` khi dùng `--release 17` | Class-file version tương ứng Java 17 |

`javap -c` disassemble instructions; `-p` hiển thị cả members không-public, bao gồm synthetic members nếu có; `-v` xem thông tin chi tiết như constant pool, flags, signatures, bootstrap methods và class attributes. Nó **không tái tạo nguyên bản AST** hay toàn bộ mã nguồn Java ban đầu.

**Không cần đoán bytecode theo từng offset.** Các nhãn branch, constant-pool index, thứ tự method hoặc chiến lược lowering có thể đổi khi dùng JDK/compiler/option khác nhưng ý nghĩa chương trình phải được giữ.

## 5. Bên trong một tệp `.class` có gì?

Tệp class là định dạng nhị phân chuẩn của JVM, không phải tệp văn bản Java hoặc tệp mã máy native. Thành phần ở mức cao:

| Thành phần | Vai trò |
| --- | --- |
| `magic` = `0xCAFEBABE` | Nhận diện class file |
| `minor_version` / `major_version` | Phiên bản định dạng class file; `--release 17` tạo major 61 với `javac` phù hợp |
| `constant_pool` | Các hằng và tham chiếu ký hiệu tới class, method, field, literal, method handle, dynamic/invokedynamic... |
| `access_flags` | Đánh dấu class/interface, public/final/abstract và các cờ khác |
| `this_class`, `super_class`, `interfaces` | Danh tính kiểu, superclass và các interface |
| `fields` | Các trường khai báo/sinh ra, descriptor và attributes |
| `methods` | Constructor, method, method synthetic/bridge, static initializer khi cần |
| `attributes` | `Code`, `StackMapTable`, `Signature`, `SourceFile`, annotations, `NestHost`/`NestMembers`, `Record`... khi áp dụng |

`Code` attribute của method có bytecode, thông tin số slot locals và operand stack cần thiết, exception handlers và có thể có line number table/metadata debug. Abstract/native methods không có `Code` theo kiểu method Java thông thường.

**Constant pool lưu các biểu diễn ký hiệu**, không phải toàn bộ địa chỉ object/method đã liên kết trong runtime. JVM còn phải loading/linking/resolution theo quy tắc riêng. Một `.class` hợp lệ có thể phụ thuộc class khác mà runtime chưa có.

`<init>` là tên đặc biệt của instance initialization/constructor ở class file; `<clinit>` là method đặc biệt cho class/interface initialization code khi cần. Những tên này không phải Java methods có thể gọi trực tiếp bằng cú pháp Java thông thường.

### 5.1. Một source file có thể sinh 0, 1 hoặc nhiều class files

- Một top-level class công khai thường sinh tệp `ClassName.class`, và nested/local/anonymous classes có thể sinh thêm tệp.
- `module-info.java` có thể sinh `module-info.class`; `package-info.java` có thể sinh `package-info.class` khi có metadata thích hợp.
- Nếu mã có lỗi, trình biên dịch không nhất thiết sinh class file tương ứng; không suy ra sự tồn tại của sản phẩm từ việc có tệp nguồn.
- Annotation processors có thể **tạo thêm source hoặc class files** theo cấu hình build. Đó là một quá trình tạo mã mở rộng có thể xảy ra trong compilation, nhưng **khác** các phép lowering cơ bản của cú pháp Java.

### 5.2. `Signature`, `SourceFile` và thông tin debug

Xóa kiểu generic không có nghĩa mọi dấu vết về generic biến mất. Compiler thường lưu thông tin kiểu tổng quát trong `Signature` attribute để tools/reflection có thể đọc; JVM linking vẫn dựa vào các descriptor sau erasure. Các attributes như `SourceFile`, `LineNumberTable`, `LocalVariableTable` hỗ trợ debug khi có hoặc được phát ra theo cấu hình, không quyết định tính đúng của toàn bộ logic.

Việc nhiều Java source constructs được chuyển về một tập instruction nhỏ hơn giải thích vì sao một decompiler **không nhất thiết tái tạo lại đúng mã nguồn ban đầu**. Nó suy diễn cấu trúc từ bytecode đã mất nhiều thông tin cú pháp.

## 6. Ý nghĩa của `--release`, `-source`, `-target` và JDK thực tế

| Tùy chọn | Mục đích |
| --- | --- |
| `javac --release 17` | Biên dịch cho phiên bản Java 17: giới hạn cú pháp/ngôn ngữ, bytecode target và API Java platform theo release tương ứng |
| `javac -source 17` | Điều khiển mức cú pháp nguồn; một mình nó không bảo đảm API của platform cũ được kiểm tra tương ứng |
| `javac -target 17` | Điều khiển class-file target; cần cấu hình thống nhất với source/API |
| `javac -g`, `-g:none` | Điều khiển một số thông tin debug được phát ra |
| `javac -d out` | Chọn thư mục chứa class files sinh ra |
| `javap -v` | Xem phiên bản class file và metadata sau compile |

`--release 17` được hỗ trợ khi dùng JDK có khả năng target Java 17. JDK quá cũ không thể target release mới hơn chính nó; JDK mới cũng có thể ngừng hỗ trợ một số release rất cũ. Trong phạm vi ví dụ của bài, chọn JDK 17+ với target 17.

Một runtime Java 17 đọc được class file major 61 trong điều kiện các dependency và API tương thích. Runtime quá cũ sẽ không hiểu class-file version mới hơn, thường gặp `UnsupportedClassVersionError`. **Đổi `import`, đóng gói JAR hay rename file không thay được class-file version.**

Compiler có thể tạo bytecode khác nhau tùy phiên bản, vì vậy dùng `javap` để quan sát **kết quả thực tế**, không lấy disassembly của một JDK làm tiêu chuẩn bắt buộc cho mọi JDK.

## 7. Lowering và các khâu liên quan nhưng không đồng nhất

- **Parsing:** đọc cú pháp và tạo cấu trúc nội bộ. Compiler chưa nhất thiết biết toàn bộ tên kiểu/overload tại thời điểm này.
- **Symbol/type attribution:** gắn tên/kiểu, quyết định overload và kiểm tra tính hợp lệ của source.
- **Annotation processing:** các annotation processors có thể phân tích model nguồn và sinh thêm mã/tài nguyên; không phải cứ có annotation là source được thay tự động.
- **Lowering:** chuyển các constructs thành biểu diễn thuận tiện cho JVM và codegen, có thể tạo methods/fields phụ trợ.
- **Class generation:** mã hóa bytecode và metadata thành `.class`. Lỗi ở các bước trước có thể ngăn sản phẩm được tạo.
- **Packaging:** gom class/resource vào JAR, WAR hoặc artifact khác; không phải chính bước hạ cấu trúc.
- **Class loading và execution:** JVM tìm lớp, liên kết, khởi tạo khi cần, rồi chạy bytecode; JIT có thể tối ưu thêm trong runtime.

Ví dụ: `javac` thành công và `LoweringDemo.class` xuất hiện chứng tỏ compiler đã tạo artifact. Chưa thể kết luận lúc chạy các thư viện ngoài đều có mặt, mọi class đều load được hoặc chương trình không gặp lỗi logic.

## 8. Lỗi thường gặp khi đọc/sinh `.class`

| Hiện tượng | Nguyên nhân/cách kiểm tra |
| --- | --- |
| `cannot find symbol` hoặc `incompatible types` | Lỗi phân giải tên hoặc kiểm tra kiểu; sửa source/import/dependency cho compiler trước khi quan sát bytecode |
| `error: invalid source release` | JDK `javac` đang dùng quá cũ hoặc không hỗ trợ mức `--release` được yêu cầu; kiểm tra `javac -version` |
| `UnsupportedClassVersionError` lúc chạy | Bytecode phát ra cho phiên bản Java cao hơn runtime; kiểm tra `javap -v` và `java -version` |
| Thiếu tệp `Outer$Nested.class` sau đóng gói | Artifact chỉ chứa `Outer.class`, đã bỏ sót nested class; kiểm tra output trước và danh sách JAR sau packaging |
| `NoSuchMethodError` / `AbstractMethodError` | Có thể do runtime sử dụng binary không tương thích với bản compiler thấy hoặc vấn đề linking; kiểm tra các dependency cùng version |
| Không thấy `lambda$...` hoặc `access$...` khi `javap` | Những tên method phụ trợ không được bảo đảm; tùy compiler, JVM target và kỹ thuật lowering |
| Decompile không giống source đã viết | Lowering, erasure và tối ưu hóa làm mất thông tin cú pháp; không coi decompiler là source gốc |
| Nghĩ mỗi dòng `.java` ứng với một instruction | Một expression có thể cần nhiều instructions, hoặc được gấp hằng; một source có thể sinh nhiều class files |

**Quy trình điều tra:**

1. Chạy lại lệnh `javac` với các options được ghi rõ (`--release`, `-encoding`, `-d`) và xem exit code.
2. Kiểm tra những tệp `.class` thật sự được tạo, đặc biệt nested/local/anonymous classes và code do processor sinh.
3. Dùng `javap -c -p` để nhìn method body; dùng `javap -v -p` nếu cần constant pool, flags hoặc metadata.
4. Nếu có tên class hoặc bridge method không quen, quay lại cấu trúc nguồn tương ứng (generic, lambda, record, nested class...); phân biệt generated member với API do con người viết.
5. Với lỗi runtime, kiểm tra class-file version, classpath/module path và dependency. Bytecode sinh đúng không bảo đảm môi trường triển khai đúng.

## 9. Câu hỏi tự kiểm tra

**1. JVM có instruction “for-each” riêng không?**  
Không. Compiler hạ `for-each` thành các thao tác phù hợp với array hoặc iterator; bytecode dùng instruction JVM hiện có.

**2. Vì sao có `WordProvider.get(): Object` dù source chỉ định nghĩa `get(): String`?**  
Do generic erasure làm descriptor phương thức interface trở thành dạng trả `Object`, compiler có thể tạo bridge method để duy trì overriding/polymorphism.

**3. Một lambda có bắt buộc sinh tệp `Outer$1.class` không?**  
Không. `javac` hiện đại thường dùng `invokedynamic`/lambda metafactory; anonymous class có hành vi sinh class file khác.

**4. Tại sao `Point` record có accessor và method khác dù source chỉ có một dòng?**  
Record quy định những thành viên được compiler sinh nếu không tự cung cấp; class file chứa bytecode/metadata thực hiện quy tắc record.

**5. `try-with-resources` chỉ là `finally { close(); }` có đúng không?**  
Không đầy đủ. Compiler phải giữ thứ tự đóng và suppressed exceptions, không làm mất exception chính nếu `close` cũng thất bại.

**6. `javap -c` có hiển thị lại cây AST gốc không?**  
Không. Nó hiển thị disassembly bytecode; phần lớn cấu trúc nguồn đã được lower hoặc xóa thông tin.

**7. Dùng JDK mới rồi `javac --release 17` có ý nghĩa gì?**  
Target hành vi compile và API platform phù hợp Java 17, sinh class-file version tương ứng để chạy trên runtime Java 17 nếu dependency tương thích.

**8. Lowering có phải JIT optimization không?**  
Không. Lowering diễn ra lúc compile source để sinh bytecode; JIT thuộc runtime, có thể chuyển bytecode thành mã máy tối ưu.

## 10. Ghi nhớ và cách áp dụng

- **Ngữ nghĩa nguồn là hợp đồng:** vòng lặp, ngoại lệ, generic dispatch, record và lambda phải hoạt động đúng với quy tắc Java.
- **Bytecode là biểu diễn thực thi:** một cấu trúc source có thể trở thành nhiều instructions, các method tổng hợp và metadata.
- **Một source có thể sinh nhiều class files:** đặc biệt khi có nested, local, anonymous hoặc generated types.
- **Dùng `javap` thay cho suy đoán:** kiểm tra class file thực sự được compiler sinh, nhưng tránh khóa logic vào offset/tên synthetic cụ thể.
- **Compiler và JVM có trách nhiệm khác nhau:** biên dịch sinh `.class`; packaging phân phối artifact; JVM nạp, liên kết và thực thi.

Điều quan trọng nhất: **hạ cấu trúc ngôn ngữ** là cầu nối giữa cách người lập trình diễn đạt thuật toán trong Java và cách bytecode JVM biểu diễn thuật toán; **sinh tệp class** là bước hiện thực hóa biểu diễn đó thành artifact nhị phân có thể kiểm tra và nạp chạy.
