# Kiểm tra bridge method, synthetic member và lớp phụ được sinh sau khi javac biên dịch

Khi `javac` biên dịch một file `.java`, đầu ra không nhất thiết chỉ có những class và method được viết tường minh trong source. Compiler có thể bổ sung **bridge methods**, **synthetic members** và những **class file phụ** phục vụ generics, overriding, nested/local/anonymous classes và các quy tắc của ngôn ngữ Java. Đây không mặc nhiên là dấu hiệu bytecode bị sửa bất thường: nhiều thành phần là cơ chế tương thích cần thiết giữa source Java và JVM.

Khi **kiểm chứng đầu ra**, người học không nên chỉ hỏi “mã đã compile thành công chưa?”. Cần biết các method và class nào thực sự xuất hiện trong `.class`, vì sao chúng có mặt, cách phân biệt method do người viết với method hỗ trợ do compiler sinh và cách tránh nhận định nhầm khi dùng reflection, bytecode analyzer, coverage tool hoặc framework quét method.

Bài này dùng Java 17+, `javac`, `javap` và reflection. Các ví dụ đầy đủ có thể tự chạy, kèm stdout, các lệnh kiểm tra bytecode và lưu ý phần nào là **hợp đồng ngôn ngữ/JVM**, phần nào chỉ là **cách triển khai của javac**.

## 1. Ba khái niệm thường bị gộp làm một

| Khái niệm | Bản chất | Dấu hiệu kiểm tra |
| --- | --- | --- |
| **Bridge method** | Method bổ trợ do compiler tạo để bảo toàn overriding/polymorphism khi chữ ký JVM khác chữ ký source, đặc biệt với **type erasure** hoặc **covariant return type** | `ACC_BRIDGE` trong `javap -v`; `Method.isBridge()` |
| **Synthetic member** | Field/method/member được compiler hoặc công cụ tạo, không tương ứng trực tiếp với một khai báo source theo nghĩa thông thường | `ACC_SYNTHETIC` / metadata synthetic; `Member.isSynthetic()` qua reflection phù hợp |
| **Class phụ được sinh** | Một file `.class` khác được tạo từ cùng nguồn, ví dụ member class, non-static inner class, local class hoặc anonymous class | Liệt kê output, xem `InnerClasses`, `EnclosingMethod`, `NestHost`/`NestMembers` nếu có |

**Quan hệ giữa chúng không phải một-một:**

- Một bridge method do `javac` sinh thường **đồng thời mang `ACC_BRIDGE` và `ACC_SYNTHETIC`**.
- Một synthetic field như tham chiếu tới instance lớp ngoài của một inner class **không phải bridge method**.
- Một nested class có file `.class` riêng **không nhất thiết là synthetic class**: source khai báo nested class đó tường minh.
- Method được compiler tạo nhưng được ngôn ngữ quy định là thành viên có thể dùng ở source, như một số method của enum/record, **không nhất thiết mang cờ synthetic**.
- Lambda có thể được hiện thực bằng `invokedynamic` và class được tạo ở runtime; **không** đồng nghĩa luôn có file `Outer$1.class` của lambda trên disk.

Đối chiếu **source-level declaration**, **JVM method descriptor**, **access flags** và **file output** thay vì chỉ đếm tên method theo trực giác.

## 2. Bridge method xuất hiện vì sao?

Generic Java thường dùng **type erasure** ở bytecode. Ví dụ interface khai báo:

~~~java
interface Holder<T> {
    T get();
}
~~~

Sau khi erase type variable `T` không có bound riêng, method descriptor của `Holder.get` tương ứng `()Ljava/lang/Object;`. Khi class triển khai:

~~~java
final class TextHolder implements Holder<String> {
    @Override
    public String get() {
        return "text";
    }
}
~~~

Implementation có descriptor `()Ljava/lang/String;`. JVM phân biệt method theo tên và descriptor, trong đó descriptor chứa kiểu trả về. Để lời gọi qua `Holder<String>` vẫn thực thi đúng implementation trong `TextHolder`, `javac` sinh một method chuyển tiếp có dạng ý tưởng:

~~~java
// Mã MINH HỌA tương đương, KHÔNG phải source được phép chép
// thêm vào TextHolder: return type overload không hợp lệ ở Java source.
public Object get() {
    return get(); // Chuyển tiếp đến String get() ở mức bytecode.
}
~~~

Tại source, **không được** tự khai báo hai method cùng tên, cùng tham số, chỉ khác kiểu trả về theo cách trên. Đó chính là chỗ cần bridge **ở cấp JVM**, không phải overload source thông thường. Method synthetic bridge giữ descriptor mà code gọi qua interface/supertype trông đợi.

Sơ đồ:

~~~text
Source:
  Holder<T>.get(): T
  TextHolder.get(): String

Erasure / JVM descriptors:
  Holder.get()      ()Ljava/lang/Object;
  TextHolder.get()  ()Ljava/lang/String;

javac tạo thêm trong TextHolder:
  get()Ljava/lang/Object;    [ACC_BRIDGE | ACC_SYNTHETIC]
       |
       +--> gọi TextHolder.get()Ljava/lang/String;
~~~

Chương trình chạy vẫn chỉ thấy giá trị `String`. Bridge là phần implementation để JVM dispatch/resolve tương thích với hợp đồng subtype.

## 3. Ví dụ Java 17 hoàn chỉnh: bridge, synthetic field và lớp inner

Tạo **một** tệp `GeneratedMembersDemo.java` ở thư mục trống:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

interface Holder<T> {
    T get();
}

final class TextHolder implements Holder<String> {
    @Override
    public String get() {
        return "text";
    }
}

final class Envelope {
    private final int base;

    Envelope(int base) {
        this.base = base;
    }

    final class Inner {
        int plus(int value) {
            return value + base;
        }
    }
}

public final class GeneratedMembersDemo {
    public static void main(String[] args) {
        Method[] methods = TextHolder.class.getDeclaredMethods();

        Arrays.sort(
                methods,
                Comparator.comparing(
                        method -> method.getReturnType().getName()
                )
        );

        for (Method method : methods) {
            if (method.getName().equals("get")) {
                System.out.println(
                        method.getName()
                        + " -> " + method.getReturnType().getSimpleName()
                        + ", bridge=" + method.isBridge()
                        + ", synthetic=" + method.isSynthetic()
                );
            }
        }

        Holder<String> holder = new TextHolder();
        System.out.println("value: " + holder.get());

        Envelope outer = new Envelope(5);
        Envelope.Inner inner = outer.new Inner();
        System.out.println("inner result: " + inner.plus(2));

        boolean syntheticOuterField = Arrays.stream(
                Envelope.Inner.class.getDeclaredFields()
        ).anyMatch(field ->
                field.isSynthetic()
                && field.getType() == Envelope.class
        );

        System.out.println(
                "synthetic outer field: " + syntheticOuterField
        );
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

**Linux/macOS (Bash):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out GeneratedMembersDemo.java
java -cp out GeneratedMembersDemo
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out GeneratedMembersDemo.java
java -cp out GeneratedMembersDemo
~~~

**Stdout chính xác với javac/JVM Java 17 của bài lab:**

~~~text
get -> Object, bridge=true, synthetic=true
get -> String, bridge=false, synthetic=false
value: text
inner result: 7
synthetic outer field: true
~~~

Giải thích:

1. `getDeclaredMethods()` trả các method **được khai báo trực tiếp trong bytecode `TextHolder`**, gồm cả bridge. Đây **không** phải API “chỉ trả method do lập trình viên viết”.
2. Reflection **không bảo đảm thứ tự** các method. Ví dụ sắp xếp theo tên đầy đủ của return type, nên `java.lang.Object` hiện trước `java.lang.String` để output có thứ tự xác định.
3. `get(): Object` do compiler sinh, có `isBridge() == true` và `isSynthetic() == true`.
4. `get(): String` là implementation viết trong source, không mang hai cờ ấy trong ví dụ.
5. `Holder<String> holder` gọi qua hợp đồng generic; kết quả `text` chứng minh cầu nối hỗ trợ dispatch đúng implementation.
6. `Envelope.Inner` là **non-static inner class** truy cập instance field `base` của `Envelope`. Với `javac` Java 17, bytecode của `Inner` có một field tổng hợp giữ tham chiếu tới instance bao ngoài; `Field.isSynthetic()` nhận diện nó.
7. Việc dùng `anyMatch` thay vì in tên field như `this$0` giúp tránh phụ thuộc vào **tên field nội bộ** do compiler chọn. Tên synthetic field không phải API public của lớp.

### Những file class được tạo

Sau khi biên dịch file nguồn duy nhất, trong `out` thông thường sẽ có:

~~~text
out/
├── Holder.class
├── TextHolder.class
├── Envelope.class
├── Envelope$Inner.class
└── GeneratedMembersDemo.class
~~~

`Envelope$Inner.class` được sinh vì source khai báo `Envelope.Inner` là một class thành viên có định nghĩa riêng. Dấu `$` là dạng tên binary name thông dụng của member class trong file class, khác cách tham chiếu `Envelope.Inner` trong source. File đó **không có nghĩa bản thân class Inner là “không có trong source”**.

Tên file của các member classes có cú pháp ổn định trong ví dụ nhưng các dạng đánh số local/anonymous class phức tạp hơn có thể phụ thuộc compiler và vị trí khai báo.

## 4. Kiểm tra bytecode bằng javap -v, -p và -c

Không cần suy luận từ output reflection: hãy mở thẳng class file bằng `javap`.

~~~bash
javap -classpath out -p -v TextHolder
~~~

Các phần quan trọng thường thấy với `javac` Java 17, lược bỏ constant pool và chỉ giữ những dòng cần kiểm tra:

~~~text
public java.lang.String get();
  descriptor: ()Ljava/lang/String;
  flags: ... ACC_PUBLIC

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  flags: ... ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

Các dòng trên là **trích đoạn minh họa**, không phải output nguyên văn (chỉ số constant pool và thứ tự chi tiết do `javap` quyết định). Số `0x....` của flags có thể được trình bày kèm tên flag.

Xem bytecode:

~~~bash
javap -classpath out -p -c TextHolder
~~~

Bridge thường có instruction gọi method implementation thực, chẳng hạn:

~~~text
public java.lang.Object get();
  Code:
     aload_0
     invokevirtual ... // Method get:()Ljava/lang/String;
     areturn
~~~

Đây là **mẫu rút gọn**; địa chỉ, tên reference và số thứ tự instruction có thể khác. Điều thiết yếu là descriptor bridge trả `Object` còn implementation trả `String`.

Để xem inner class (Bash và PowerShell đều hỗ trợ chuỗi single quote):

~~~bash
javap -classpath out -p -v 'Envelope$Inner'
~~~

Tìm field kiểu `Envelope` có `ACC_SYNTHETIC` và thông tin class lồng trong các attributes. Chú ý:

- Trong **Bash**, viết `Envelope$Inner` không quote có thể khiến shell mở rộng `$Inner` như biến môi trường.
- Trong **PowerShell**, double quote có thể nội suy `$Inner`; single quote giữ nguyên.
- Trong **CMD**, có thể dùng `"Envelope$Inner"` để truyền nguyên vẹn tên class.

Xem danh sách class file trên Linux/macOS:

~~~bash
find out -type f -name '*.class' -print | sort
~~~

Trên PowerShell:

~~~powershell
Get-ChildItem -Path out -Recurse -Filter *.class |
    Select-Object -ExpandProperty FullName
~~~

**Đừng dùng `javap -c` một mình để kết luận synthetic:** nó chủ yếu in instructions, còn muốn xác minh cờ thì dùng `-v` (verbose), và muốn thấy non-public members thì dùng `-p`.

## 5. Reflection: nhận diện bridge và synthetic một cách đúng đắn

API reflection có các phương thức:

| API | Ý nghĩa |
| --- | --- |
| `Method.isBridge()` | Method có cờ bridge theo metadata class file |
| `Method.isSynthetic()` | Method được đánh dấu synthetic |
| `Field.isSynthetic()` | Field được đánh dấu synthetic |
| `Constructor.isSynthetic()` | Constructor được đánh dấu synthetic nếu có |
| `Class.isSynthetic()` | Kiểm tra synthetic flag của runtime class |
| `Class.getDeclaredMethods()` | Các method trực tiếp của class, kể cả compiler-generated methods |
| `Class.getMethods()` | Các public methods có thể thấy theo quy tắc reflection, gồm inherited methods |
| `Class.getDeclaredFields()` | Các field khai báo trực tiếp, kể cả field compiler tạo |

Lưu ý `isBridge()` là phương thức của **`Method`**, không phải của mọi `Member`. Một synthetic field không có bridge flag. Một class phụ được tạo từ khai báo source vẫn có thể trả `Class.isSynthetic() == false`.

### Lọc bridge khi công cụ quét method

Giả sử một framework tạo danh sách các hành động dựa trên public methods. Nếu lặp `getDeclaredMethods()` và coi mỗi method name là một endpoint riêng, có thể đăng ký trùng `get()` của `TextHolder`:

~~~java
for (Method method : TextHolder.class.getDeclaredMethods()) {
    if (method.isBridge() || method.isSynthetic()) {
        continue;
    }
    // Xử lý những method phù hợp chính sách framework.
}
~~~

Đây là **fragment**; cần import `java.lang.reflect.Method` và đặt trong method phù hợp.

Bộ lọc này là một **chính sách ứng dụng**, không phải quy tắc bắt buộc cho mọi framework. Ví dụ công cụ đo bytecode coverage, framework serialization hoặc proxy system đôi khi cần phân tích cả synthetic/bridge methods. Một annotation processor phân tích source qua `javax.lang.model` cũng không nhất thiết hiển thị cùng danh sách method mà runtime reflection thấy trong bytecode.

**Đừng lọc chỉ theo tên** như `get` hoặc ký tự `$`. Method do người viết cũng có thể dùng dấu `$` hợp lệ trong identifier; ngược lại method compiler sinh có thể mang tên bình thường. Nên dựa vào metadata và mục tiêu phân tích.

### Tại sao signature trên reflection dễ gây hiểu nhầm?

Java source không cho phép overload chỉ khác return type, nhưng reflection có thể thấy hai method:

~~~text
get() -> java.lang.String
get() -> java.lang.Object
~~~

Điều này không phải source vi phạm Java. **Class file** và **source language** có quy tắc biểu diễn method khác nhau; bridge do compiler sinh giúp chuyển giữa hai hệ đó.

Trong code kiểm chứng, nên đọc cả **`getReturnType()`**, **`getParameterTypes()`**, **`isBridge()`**, **`isSynthetic()`** và generic signature nếu cần. `getGenericReturnType()` hỗ trợ phân tích kiểu generic mà class file còn lưu metadata tương ứng; nó không biến method bridge thành khai báo source độc lập.

## 6. Bridge method do generic erasure với tham số: checkcast trong bytecode

Ví dụ `Holder<T>.get()` tạo bridge khác ở return type. Với **tham số generic**, bridge có thể phải ép kiểu đối số trước khi gọi implementation.

Tạo tệp độc lập **`BridgeCastDemo.java`**:

~~~java
interface Sink<T> {
    void put(T value);
}

final class StringSink implements Sink<String> {
    @Override
    public void put(String value) {
        System.out.println("stored:" + value);
    }
}

public final class BridgeCastDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        Sink<String> typed = new StringSink();
        typed.put("ok");

        Sink raw = new StringSink();
        try {
            raw.put(Integer.valueOf(7));
        } catch (ClassCastException ex) {
            System.out.println("bridge rejected Integer");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
mkdir -p out-cast
javac --release 17 -encoding UTF-8 -d out-cast BridgeCastDemo.java
java -cp out-cast BridgeCastDemo
~~~

**Stdout chính xác:**

~~~text
stored:ok
bridge rejected Integer
~~~

Ở `Sink<T>`, method bị erase thành `put(Object)`, còn implementation khai báo `put(String)`. Compiler tạo bridge tương đương về ý nghĩa:

~~~java
// Chỉ để giải thích bytecode, KHÔNG phải method source hợp lệ
public void put(Object value) {
    put((String) value);
}
~~~

Gọi `raw.put(Integer.valueOf(7))` ở runtime đi qua bridge `put(Object)`, lệnh cast sang `String` thất bại, nên `ClassCastException` xảy ra **trước khi** body `put(String)` được chạy. `@SuppressWarnings` chỉ dùng để giảm cảnh báo unchecked/raw ở **đoạn cố ý minh họa việc bỏ an toàn kiểu**, không làm phép gọi đó an toàn.

Inspect bytecode:

~~~bash
javap -classpath out-cast -p -c -v StringSink
~~~

Ở method synthetic bridge `put(java.lang.Object)`, tìm cờ `ACC_BRIDGE, ACC_SYNTHETIC` và instruction dạng `checkcast java/lang/String` trước lời gọi `put(java.lang.String)`. Chính chi tiết này giải thích vì sao bridge không chỉ là “method bị nhân đôi”, mà có thể chứa bytecode chuyển đổi cần thiết.

### Tránh hiểu nhầm về raw type

Mã Java dùng generic đúng kiểu không thể truyền `Integer` cho `Sink<String>` ở compile-time. Raw type làm mất kiểm tra kiểu generic của lời gọi, nhưng bridge/runtime cast vẫn bảo vệ type implementation. Đây là **ClassCastException runtime do sử dụng raw reference**, không phải `javac` chọn nhầm overload.

## 7. Covariant return type cũng có thể sinh bridge

Bridge không chỉ gắn với generics. Khi subclass override một method với kiểu trả về **hẹp hơn** (covariant return), method descriptor JVM có thể khác giữa superclass và subclass.

Ví dụ tệp **`CovariantBridgeDemo.java`**:

~~~java
class ParentValue {
    Number value() {
        return 1;
    }
}

final class IntegerValue extends ParentValue {
    @Override
    Integer value() {
        return 2;
    }
}

public final class CovariantBridgeDemo {
    public static void main(String[] args) {
        ParentValue value = new IntegerValue();
        System.out.println(value.value());
    }
}
~~~

Chạy:

~~~bash
mkdir -p out-covariant
javac --release 17 -encoding UTF-8 -d out-covariant CovariantBridgeDemo.java
java -cp out-covariant CovariantBridgeDemo
~~~

**Stdout chính xác:**

~~~text
2
~~~

Compiler có thể sinh một bridge trong `IntegerValue` với descriptor trả `Number`, chuyển tiếp tới implementation trả `Integer`. Xem:

~~~bash
javap -classpath out-covariant -p -v IntegerValue
~~~

Với `javac` Java 17, bridge có `ACC_BRIDGE` và `ACC_SYNTHETIC`. Nó giữ hành vi overriding đúng khi mã gọi qua kiểu compile-time `ParentValue`.

**Ghi nhớ:** JVM có thể phân biệt các descriptor có return type khác nhau, nhưng Java source-level override không được triển khai bằng cách viết hai overload chỉ khác return type. Bridge là công việc sinh bytecode của compiler.

## 8. Synthetic field của non-static inner class

Một **non-static inner class** có quyền truy cập instance của lớp bao ngoài. Để thực hiện lời truy cập này ở runtime, `javac` có thể lưu tham chiếu instance bao ngoài trong một field được compiler sinh.

Trong `GeneratedMembersDemo`:

~~~java
final class Envelope {
    private final int base;

    Envelope(int base) {
        this.base = base;
    }

    final class Inner {
        int plus(int value) {
            return value + base;
        }
    }
}
~~~

Source chỉ khai báo `base` trong `Envelope`, không khai báo field `outer` trong `Inner`. Tuy nhiên `Inner.plus()` phải biết **instance Envelope nào** để đọc `base`. Khi viết `outer.new Inner()`, compiler chuyển tham chiếu outer vào cơ chế khởi tạo inner class.

Dùng `javap -p -v 'Envelope$Inner'` để xem field tổng hợp tham chiếu tới `Envelope`. Với `javac` Java 17, field này thường có tên nội bộ như `this$0` và cờ `ACC_SYNTHETIC`.

### Synthetic và việc tham chiếu outer không giống nhau

Không nên suy ra mọi inner class đều có chính xác field tên `this$0` trên **mọi JDK/compiler**. Cách triển khai capture tham chiếu outer có thể khác và được tối ưu trong các điều kiện nhất định. Ví dụ lab trực tiếp sử dụng `base` để tạo tình huống rõ ràng ở Java 17.

Cũng không nên xem field synthetic này là dữ liệu nghiệp vụ cần serialize. Khi một framework quét fields để tạo JSON hoặc SQL schema, nếu không lọc đúng nó có thể đưa cả tham chiếu outer vào mô hình, gây chu kỳ object graph hoặc rò thông tin không mong muốn.

### Vì sao private access không nhất thiết tạo access$000 nữa?

Một số bài cũ mô tả compiler phải sinh synthetic accessor như `access$000` để inner class truy cập private field/method ở outer. Với class file đời cũ, đây là một kỹ thuật thường gặp.

Từ Java 11, JVM hỗ trợ **nest-based access control** và class file có attributes như `NestHost` và `NestMembers`. Khi compile cho Java 17, `javac` thường dùng khả năng nestmates để cho inner/outer classes truy cập private members, **không cần sinh accessor theo mẫu cũ trong nhiều trường hợp**.

Vì vậy không dùng câu hỏi “có method `access$000` hay không?” làm bài test bắt buộc cho mọi compiler/JDK. Hãy kiểm tra class file đang có bằng `javap -v -p`, đọc cả **nest attributes** và synthetic methods nếu xuất hiện.

## 9. Member class, local class và anonymous class: một source, nhiều file .class

Java có những loại type khai báo khác nhau:

| Loại | Ví dụ | File class bổ sung |
| --- | --- | --- |
| Static nested class | `static class Helper` trong outer class | Thường có `Outer$Helper.class` |
| Non-static inner member class | `class Inner` trong outer class | Thường có `Outer$Inner.class` |
| Local class | `class LocalTask` khai báo trong một method | Có class file riêng; phần đánh số/tên binary do compiler quyết định |
| Anonymous class | `new Runnable() { ... }` | Có class file riêng; tên nội bộ thường có dấu `$` và số |
| Lambda expression | `() -> ...` | Không nhất thiết có class file tương ứng trên disk; thường dùng `invokedynamic` và runtime machinery |

Ví dụ một chương trình **`GeneratedClassesDemo.java`**:

~~~java
public final class GeneratedClassesDemo {
    interface Task {
        String run();
    }

    public static void main(String[] args) {
        class LocalTask implements Task {
            @Override
            public String run() {
                return "local";
            }
        }

        Task anonymous = new Task() {
            @Override
            public String run() {
                return "anonymous";
            }
        };

        Task lambda = () -> "lambda";

        System.out.println(new LocalTask().run());
        System.out.println(anonymous.run());
        System.out.println(lambda.run());
    }
}
~~~

Chạy:

~~~bash
mkdir -p out-classes
javac --release 17 -encoding UTF-8 -d out-classes GeneratedClassesDemo.java
java -cp out-classes GeneratedClassesDemo
~~~

**Stdout chính xác:**

~~~text
local
anonymous
lambda
~~~

Dùng:

~~~bash
find out-classes -type f -name '*.class' -print | sort
javap -classpath out-classes -p -v GeneratedClassesDemo
~~~

Thông thường bạn sẽ thấy file cho outer, member interface `Task`, local class `LocalTask` và anonymous class. **Đừng hardcode** tên đánh số như `GeneratedClassesDemo$1` hay `GeneratedClassesDemo$1LocalTask` vào bài test chạy trên nhiều compiler/phiên bản: tên có thể đổi khi thêm/bớt khai báo hoặc thay compiler.

### Phân biệt “class phụ được sinh” và “synthetic class”

Cả local class và anonymous class đều xuất phát từ **cú pháp Java source hợp lệ**; class file riêng là cách lưu định nghĩa của chúng. Một file có dấu `$` trong tên **không chứng minh** cả class là synthetic.

Khi kiểm tra reflection:

- `Class.isMemberClass()` nhận diện member class theo quy tắc API.
- `Class.isLocalClass()` nhận diện local class.
- `Class.isAnonymousClass()` nhận diện anonymous class.
- `Class.getEnclosingMethod()` có thể chỉ method chứa khai báo local/anonymous class.
- `Class.isSynthetic()` là phép kiểm tra **khác** với ba phân loại trên.

Không lọc toàn bộ file có dấu `$` rồi gắn nhãn “không do người viết”, vì static nested class cũng có file `$` nhưng được source khai báo tường minh.

## 10. Lambda: không mặc định có Outer$1.class

Khi nhìn source:

~~~java
Runnable action = () -> System.out.println("run");
~~~

Một người mới học có thể tưởng `javac` luôn tạo `Outer$1.class` như anonymous class. Với Java 17, lambda thông thường được biên dịch dựa trên **`invokedynamic`** và bootstrap machinery phù hợp; cách tạo runtime implementation khác anonymous class truyền thống.

Xem một class có lambda bằng:

~~~bash
javap -classpath out-classes -p -c -v GeneratedClassesDemo
~~~

Tìm:
- Instruction `invokedynamic` trong bytecode method chứa lambda.
- `BootstrapMethods` attribute mô tả bootstrap method liên quan.
- Method hỗ trợ do compiler sinh, có thể có tên như `lambda$main$0` và được đánh dấu synthetic trong một số trường hợp.

**Không cam kết** method hỗ trợ có tên chính xác `lambda$main$0` trong mọi bản compiler hoặc rằng mọi lambda đều có một method synthetic riêng. JVM và compiler được phép dùng những chiến lược triển khai khác nhau khi vẫn tuân theo hành vi ngôn ngữ.

Ở runtime, implementation của lambda cũng có thể dùng **hidden classes**. Chúng không bắt buộc được xuất thành `.class` trên disk khi `javac` chạy. Vì thế “không thấy file lambda phụ” **không phải** lỗi build.

### Anonymous class và lambda khác nhau về this

Trong anonymous class, `this` chỉ instance của anonymous class đó. Trong lambda, `this` (ở ngữ cảnh instance) là `this` của lớp bao quanh. Sự khác biệt source semantics này giải thích vì sao compiler không buộc phải triển khai cả hai bằng cùng một cấu trúc class file.

Không suy ra tên runtime class của lambda bằng cách gọi `lambda.getClass().getName()` rồi cố xây logic nghiệp vụ dựa trên chuỗi ấy. Tên/định danh triển khai có thể thay đổi theo JVM/JDK và không phải API ổn định.

## 11. Các synthetic members khác: đừng suy luận quá mức

Một số hình thức bytecode do compiler tạo còn bao gồm:

- Field tổng hợp lưu captured values trong một số local/anonymous classes.
- Field tổng hợp giữ outer instance của non-static inner class trong một số trường hợp.
- Bridge methods để nối descriptor của generic erasure/covariant return.
- Các method hỗ trợ lambda, switch hoặc những construct được javac dịch thành bytecode bổ trợ, tùy version/chiến lược.
- Một số helper fields/methods phục vụ enum hoặc lớp được tạo bởi compiler.

Tuy nhiên có các điểm cần tránh:

1. **Synthetic không đồng nghĩa private.** Compiler có thể tạo bridge **public**; field synthetic có thể mang access flags khác.
2. **Không phải member tự động được sinh nào cũng synthetic.** Một số method do Java language mandate có vai trò public API, ví dụ `values()` và `valueOf(String)` của enum. Đừng mặc định chúng có `Method.isSynthetic() == true`.
3. **Không phải mọi anonymous/local class đều synthetic.** Sự tồn tại class file riêng chưa đủ chứng minh `ACC_SYNTHETIC`.
4. **Không phải mọi bytecode instruction bổ trợ đều có một member synthetic tương ứng.** Compiler có thể dùng instruction trực tiếp, `invokedynamic`, constant pool entry hoặc attributes.
5. **Không dùng prefix `access$`, `lambda$` hoặc `this$` như tiêu chuẩn duy nhất.** Tên internal là chi tiết triển khai. Cờ và metadata class file, cùng ngữ cảnh compiler, mới có giá trị chẩn đoán.

Sự phân biệt này quan trọng khi viết hệ thống kiểm chứng bytecode lâu dài: bài test dựa trên **hành vi và contract** bền hơn bài test yêu cầu một tập tên internal duy nhất mà đặc tả không bảo đảm.

## 12. Kiểm chứng class output như một artifact

Sau mỗi lượt compile, nên kiểm chứng theo ba lớp:

### 12.1. Xác nhận compile thành công và liệt kê file

Trên Linux/macOS:

~~~bash
javac --release 17 -encoding UTF-8 -d out GeneratedMembersDemo.java
find out -type f -name '*.class' -print | sort
~~~

Trên PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 -d out GeneratedMembersDemo.java
Get-ChildItem -Path out -Recurse -Filter *.class |
    Select-Object -ExpandProperty FullName
~~~

Trước khi chạy phải có thư mục `out`; các mục trước đã nêu lệnh tạo. Xác minh các file có mặt và đọc lại metadata nếu cần, nhưng nhớ rằng số lượng class file có thể đổi khi source đổi hoặc compiler thay đổi chiến lược triển khai.

### 12.2. Xem method flags, descriptor, attributes

~~~bash
javap -classpath out -p -v TextHolder
javap -classpath out -p -v 'Envelope$Inner'
javap -classpath out -p -c TextHolder
~~~

Các mục cần ghi nhận:

- Binary name/superclass/interfaces.
- Method descriptors bên cạnh generic `Signature` attribute nếu có.
- `ACC_BRIDGE` và `ACC_SYNTHETIC` trên method.
- Synthetic field mà inner class dùng để trỏ về outer.
- `InnerClasses` và nest attributes (nếu có).
- Bytecode dispatch, `invokevirtual` hoặc `checkcast` trong bridge.
- Class file major version phù hợp release đang nhắm đến.

### 12.3. Chạy kiểm chứng hành vi

~~~bash
java -cp out GeneratedMembersDemo
~~~

Reflection và stdout từ bài lab giúp kiểm chứng flags/behavior, chứ không chỉ số file. Với dự án nhiều module/JAR, đảm bảo runtime classpath và class loader dùng đúng artifact vừa biên dịch; nếu runtime vô tình tải class khác cùng binary name, kết luận từ `javap` trên output của bạn có thể không mô tả class đang chạy.

## 13. Kiểm thử bằng reflection mà không phụ thuộc thứ tự method

Khi xây automated tests, tránh:

~~~java
Method first = TextHolder.class.getDeclaredMethods()[0];
// Sai cách kiểm chứng nếu trông đợi first luôn là String get().
~~~

Reflection API không bảo đảm thứ tự trả về của method arrays. Cũng tránh chỉ kiểm tra `getDeclaredMethods().length == 2` trên class phức tạp: compiler có thể sinh member hỗ trợ khác, hoặc framework bytecode enhancement có thể can thiệp vào class.

Một chiến lược tốt hơn là lọc theo thuộc tính:

~~~java
long bridgeCount = Arrays.stream(
        TextHolder.class.getDeclaredMethods()
).filter(Method::isBridge).count();

long syntheticBridgeCount = Arrays.stream(
        TextHolder.class.getDeclaredMethods()
).filter(m -> m.isBridge() && m.isSynthetic()).count();

System.out.println(bridgeCount);
System.out.println(syntheticBridgeCount);
~~~

Đây là **fragment** cần đặt trong method và import `java.lang.reflect.Method`, `java.util.Arrays`. Với `TextHolder` từ bài lab Java 17, hai dòng in:

~~~text
1
1
~~~

Trong test framework, nên kiểm tra cả **descriptor đúng** và method thật được dispatch tới implementation, nếu việc đảm bảo ABI là mục tiêu. Chỉ thấy `isBridge() == true` chưa chứng minh bridge có bytecode hợp lệ hoặc hành vi đúng sau bytecode rewriting.

Một test bytecode chi tiết có thể dùng `javap -v` hoặc một thư viện đọc class file theo class version được hỗ trợ, nhưng phải giữ ranh giới giữa kiểm tra flags và kiểm tra hành vi.

## 14. ABI compatibility: bridge có thể ảnh hưởng code đã compile

Bridge methods giúp giữ khả năng gọi method qua interface/superclass đã bị erase. Nếu một công cụ bytecode optimizer, obfuscator hoặc transformer xóa method `ACC_BRIDGE` chỉ vì nó synthetic, mã compile trước đó có thể thất bại khi runtime phải resolve descriptor mong đợi.

Chẳng hạn, một caller compile theo interface `Holder<T>` mong method `Holder.get(): Object`. Trong `TextHolder`, bridge `get(): Object` đảm bảo dispatch tới `get(): String`. Nếu xóa bridge trong một hierarchy không còn method matching cần thiết, hành vi virtual dispatch có thể sai hoặc gây lỗi liên kết/dispatch runtime, tùy class layout cụ thể.

**Không được kết luận:** “Synthetic luôn là rác, có thể xóa để giảm kích thước JAR.” Synthetic/bridge flags là metadata giải thích **nguồn gốc và vai trò** của member; compiler-generated member có thể là **điều kiện bắt buộc** để chương trình vẫn tuân thủ overriding sau erasure.

Các công cụ shrink/obfuscate cần bảo toàn:
- Method descriptors cần thiết cho ABI.
- Bridge methods và quan hệ dispatch theo bytecode specification.
- Reflection entry points mà ứng dụng/framework dùng.
- Metadata/attributes cần thiết cho ngữ nghĩa của các tính năng ngôn ngữ hoặc frameworks được cấu hình.

Việc đổi generic signature chỉ có thể làm compile-time type checking khác, trong khi descriptor JVM và bridge quyết định cách gọi binary thực tế. Khi gỡ lỗi `NoSuchMethodError` hoặc `AbstractMethodError` sau tối ưu hóa bytecode, hãy xem bridge còn hay bị thay đổi không.

## 15. Lớp phụ trong JAR và các vấn đề đóng gói

Giả sử bạn đóng gói:

~~~bash
jar --create --file app.jar -C out .
jar --list --file app.jar
~~~

Nếu `out` chứa `GeneratedMembersDemo.class`, `TextHolder.class` và `Envelope$Inner.class`, JAR phải chứa các class file cần thiết để runtime tải. Đóng **chỉ class có main** mà bỏ mất inner/helper classes có thể gây `NoClassDefFoundError` khi code lần đầu sử dụng chúng.

Ngược lại, đừng nhận diện mọi file `Outer$X.class` là artifact thừa. Đây có thể là member type public do source định nghĩa; xóa sẽ phá API.

### Kể cả source file duy nhất cũng có thể tạo nhiều class

Bài lab có năm class files từ một file `GeneratedMembersDemo.java`. Điều đó hợp lệ. Trong build system, khi source đổi/xóa một local/anonymous class, cần xóa stale class files tương ứng từ lần compile cũ; nếu không, JAR có thể giữ bytecode không còn thuộc source hiện tại.

Khả năng **clean build** và **incremental build** vì thế là vấn đề riêng ngoài `javac` sinh bytecode đúng. Khi phát hiện một class phụ “không có trong source nữa”, kiểm tra output directory có được clean/invalidated đúng hay không trước khi quy kết compiler lỗi.

### Classfile versions và cách javac triển khai có thể thay đổi

Khi dùng `--release 8` so với `--release 17` (nếu compiler hỗ trợ cả hai), compiler có thể sinh khác nhau về synthetic accessors và nest metadata. Để so sánh đúng:

1. Biên dịch cùng source ở hai thư mục output **riêng biệt**.
2. Xem `major version` của mỗi class.
3. Dùng `javap -v -p` để so flags/attributes.
4. Không thay đổi runtime target giữa các lần test khi đang kiểm tra một thuộc tính cụ thể.
5. Chỉ coi những khác biệt được đặc tả là điều kiện bắt buộc; chi tiết helper method có thể phụ thuộc phiên bản compiler.

## 16. Những sai lầm khi đọc kết quả javap hoặc reflection

| Nhận định/lỗi | Cách hiểu đúng |
| --- | --- |
| “Một file source phải tạo đúng một .class” | Nested/local/anonymous types có thể tạo nhiều class files |
| “Hai method get() khác return type chứng minh source overload sai” | Một method có thể là **bridge** do compiler tạo ở bytecode level |
| “Mọi bridge method đều là method do người viết” | `ACC_BRIDGE` cho biết cầu nối do compiler tạo; trong javac thường cùng `ACC_SYNTHETIC` |
| “Mọi synthetic member đều có thể xóa” | Có thể bắt buộc cho dispatch, capture, runtime access hoặc ABI |
| “getDeclaredMethods chỉ trả source methods” | Nó có thể trả bridge/synthetic methods tồn tại trong class file |
| “Thứ tự getDeclaredMethods luôn giữ thứ tự source” | Reflection không bảo đảm order |
| “File có dấu $ chắc chắn synthetic” | Có thể là member class tường minh, local hoặc anonymous class |
| “Mọi lambda có Outer$1.class” | Lambda thường dựa trên `invokedynamic` và runtime implementation |
| “Nếu dùng Java 17 luôn có access$000” | Nest-based access control có thể loại bỏ nhu cầu accessor kiểu cũ |
| “isSynthetic() == false nghĩa là người dùng tự viết method” | Một số generated/mandated methods không mang synthetic flag |
| “Compiler sinh helper thì đó là lỗi build” | Có thể là bytecode bắt buộc để thực hiện ngữ nghĩa Java |
| “Class file trên disk và class runtime chắc chắn giống nhau” | Runtime classpath/loader có thể tải một bản khác cùng binary name |

## 17. Quy trình rà soát đầu ra có thể lặp lại

Khi gặp nghi vấn bridge/synthetic trong dự án thật:

1. **Cố định nguồn và JDK**: lưu `javac -version`, `--release`, các option processor/plugin và compile classpath.
2. **Biên dịch vào output sạch**: loại class stale của lần build cũ; không sửa trực tiếp output của dự án đang chạy.
3. **Liệt kê toàn bộ .class files**: nhận diện nested/member/local/anonymous classes và class phụ.
4. **Chạy `javap -p -v -c`** trên class nghi vấn; đọc method descriptors, access flags, `Signature`, `InnerClasses` và nest attributes.
5. **Đối chiếu generic/covariant inheritance**: nếu method override có descriptor khác sau erasure/covariance, bridge có thể cần để giữ polymorphism.
6. **Dùng reflection đúng đắn**: lọc method theo `isBridge`/`isSynthetic` nếu mục tiêu là source-like API; không mặc định loại bỏ khi kiểm tra ABI.
7. **Kiểm thử virtual dispatch và cast**: gọi qua kiểu interface/superclass, kiểm tra hành vi của bridge.
8. **Đóng gói đầy đủ**: giữ helper classes và resources cần thiết trong artifact, kiểm tra JAR thay vì chỉ class main.
9. **Đối chiếu runtime loader**: class có thể đến từ JAR khác; kiểm tra CodeSource/class loader nếu kết quả lệch với bytecode trên disk.
10. **Đánh dấu rõ chi tiết phụ thuộc compiler**: đừng biến tên synthetic field, numbering anonymous classes hoặc cấu trúc lambda nội bộ thành hợp đồng API vĩnh viễn.

## 18. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `TextHolder` implements `Holder<String>`, khai báo `String get()`. Vì sao bytecode có thêm `Object get()`?

**Đáp án:** Vì erasure của `Holder<T>.get` cho descriptor trả `Object`. Bridge giữ hợp đồng runtime dispatch tương thích với method của interface; implementation nguồn trả `String`.

**Câu 2.** Trong `TextHolder` của `javac` Java 17, `get():Object` có `Method.isBridge()` và `isSynthetic()` bằng bao nhiêu?

**Đáp án:** Đều `true`. Method `get():String` của source thì cả hai bằng `false` trong lab.

**Câu 3.** Một class inner dùng field của instance outer. Reflection thấy một synthetic field kiểu outer. Có phải source đã khai báo field đó không?

**Đáp án:** Không. Compiler tạo field hỗ trợ tham chiếu outer. Tên chính xác là chi tiết triển khai, không nên dùng làm business API.

**Câu 4.** Tại sao `Envelope$Inner.class` không có nghĩa `Envelope.Inner` là synthetic type?

**Đáp án:** Source đã khai báo `Inner` tường minh; file riêng là dạng biên dịch của member class. Tên có `$` không phải cờ `ACC_SYNTHETIC`.

**Câu 5.** Khi gọi `raw.put(Integer.valueOf(7))` qua `Sink` dạng raw, vì sao xảy ra `ClassCastException`?

**Đáp án:** Bridge `put(Object)` chuyển tiếp tới `put(String)` và phải `checkcast String`; đối số Integer không tương thích, nên ném lỗi trước body method nhận String.

**Câu 6.** Một lambda `() -> "hello"` luôn tạo file `Outer$1.class` khi javac compile không?

**Đáp án:** Không. Java 17 thường dùng `invokedynamic` và bootstrap/runtime implementation; class có thể được tạo ở runtime thay vì là file phụ trên disk.

**Câu 7.** Vì sao tool quét API phải cẩn thận với `getDeclaredMethods()`?

**Đáp án:** Kết quả bao gồm methods có trong class file, có thể có compiler-generated bridge/synthetic methods; thứ tự cũng không được bảo đảm. Tool phải lọc/nhóm theo mục đích.

**Câu 8.** Có thể xóa mọi method synthetic khỏi JAR để tiết kiệm dung lượng không?

**Đáp án:** Không. Bridge/capture/helper members có thể cần cho runtime behavior và binary compatibility. Việc tối ưu phải duy trì ngữ nghĩa và các method descriptors cần thiết.

**Câu 9.** Tại sao sau khi nâng JDK, `access$000` có thể biến mất?

**Đáp án:** Với nest-based access control của class files hiện đại, compiler có thể cho phép nestmates truy cập private members mà không cần helper access method theo mẫu cũ.

**Câu 10.** Kiểm tra `Method.isBridge()` có thay thế việc chạy chương trình không?

**Đáp án:** Không. Flag xác nhận metadata, nhưng bytecode có thể bị chỉnh sửa hoặc phụ thuộc runtime khác. Muốn kiểm chứng hành vi, phải gọi qua các kiểu interface/superclass, chạy test và đối chiếu artifact thực tải.

## Ghi nhớ

- **Bridge method** là method bổ trợ ở bytecode level cho generic erasure hoặc covariant return; với `javac` thường mang **`ACC_BRIDGE` và `ACC_SYNTHETIC`**.
- **Synthetic member** là metadata về nguồn gốc compiler/tool, không mặc định thừa, không đồng nghĩa private và không đồng nghĩa có thể xóa.
- **Một file .java có thể sinh nhiều .class**; nested/local/anonymous classes và lambda có cơ chế triển khai khác nhau.
- Dùng **`javap -p -v -c`** để đọc flags, descriptors và bytecode; dùng **`Method.isBridge()` / `Member.isSynthetic()`** để xác minh qua reflection.
- **Không phụ thuộc tên nội bộ** như `this$0`, `access$000`, `lambda$...` hoặc số thứ tự anonymous class làm hợp đồng API xuyên mọi JDK/compiler.
- Kiểm chứng đầu ra tốt cần **biên dịch vào output sạch, kiểm tra class files/flags, chạy test dispatch và giữ các class phụ cần thiết khi đóng gói**.
