# Bridge method và synthetic member trong đầu ra biên dịch Java

## 1. Mục tiêu của bài

Mã nguồn Java không luôn tương ứng một-một với các method và field được lưu trong tệp .class. Trình biên dịch có thể tạo thêm thành phần để giữ nguyên ngữ nghĩa của ngôn ngữ sau khi chuyển sang bytecode. Hai trường hợp đáng học là:

- **Bridge method**: phương thức trung gian compiler tạo để duy trì overriding và dynamic dispatch khi method ở mức bytecode có descriptor khác với method đã được chuyên biệt trong source. Thường gặp với generic type erasure và covariant return.
- **Synthetic member**: thành phần được đánh dấu có nguồn gốc từ biên dịch, không tương ứng trực tiếp với khai báo nguồn bình thường. Nhiều method/field mang cờ **ACC_SYNTHETIC** trong class file.

Bridge method thường cũng là synthetic method trong đầu ra javac, nhưng synthetic member có phạm vi rộng hơn. Không phải mọi method do compiler tạo là bridge; cũng không phải mọi thành phần compiler tự tạo đều được đánh dấu synthetic.

Sau bài, bạn sẽ tự biên dịch Java 17+, tìm bridge bằng javap, kiểm tra cờ ACC_BRIDGE và ACC_SYNTHETIC, so sánh với Reflection, giải thích generic erasure và covariant return, đồng thời hiểu giới hạn khi phân tích đầu ra của các compiler khác nhau.

## 2. Từ Java source signature đến JVM descriptor

Trong Java source, overriding được xét theo tên method, tham số, quan hệ kiểu, giới hạn generic, return-type substitutability và các quy tắc visibility/static/final. Trên JVM, method được lưu với **descriptor** mô tả danh sách kiểu tham số **và kiểu trả về**.

~~~text
String process(String input)
    descriptor: (Ljava/lang/String;)Ljava/lang/String;

Object process(Object input)
    descriptor: (Ljava/lang/Object;)Ljava/lang/Object;

Number read()
    descriptor: ()Ljava/lang/Number;

Integer read()
    descriptor: ()Ljava/lang/Integer;
~~~

Một số ký hiệu:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| Ljava/lang/String; | Tham chiếu java.lang.String |
| Ljava/lang/Object; | Tham chiếu java.lang.Object |
| I | int |
| V | void |
| (I)V | Nhận int, trả void |
| ()Ljava/lang/Number; | Không có tham số, trả Number |

Ở Java source, không thể overload chỉ bằng sự khác biệt kiểu trả về. Tuy nhiên, descriptor của bytecode có cả kiểu trả về; compiler có thể tạo hai method cùng tên và tham số nhưng khác kiểu trả về trong .class, điều người viết không thể tự khai báo thành hai method Java bình thường.

**Điểm quan trọng:** đọc một dòng javap hiển thị kiểu generic T không đủ để biết descriptor JVM. Cần xem javap -v để quan sát descriptor sau type erasure và metadata Signature.

## 3. Vì sao generic type erasure cần bridge?

Giả sử lớp cha định nghĩa:

~~~java
public class Processor<T> {
    public T process(T input) {
        return input;
    }
}
~~~

Với T không có upper bound cụ thể, type erasure thay T bằng Object ở descriptor JVM:

~~~text
Processor.process:
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Lớp con chuyên biệt hóa T thành String:

~~~java
public final class StringProcessor extends Processor<String> {
    @Override
    public String process(String input) {
        return input.strip();
    }
}
~~~

Java compiler xác nhận process(String) là override hợp lệ với method kế thừa từ Processor<String>. Nhưng method nguồn trong lớp con được biên dịch với descriptor:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

Nếu chỉ có method đó, JVM sẽ không thấy cùng descriptor với method process(Object):Object của Processor khi thực hiện lời gọi qua kiểu cha đã erase. Để bảo toàn dispatch, javac sinh một method trung gian trong StringProcessor có descriptor process(Object):Object. Logic tương đương:

~~~text
StringProcessor.process(Object):Object   [bridge]
        |
        v
checkcast tham số thành String
        |
        v
StringProcessor.process(String):String   [method từ source]
        |
        v
Trả String như Object
~~~

Đó là bridge method. Nó bảo đảm mã client gọi thông qua tham chiếu Processor<String> vẫn thực thi implementation StringProcessor. Generics không tạo thêm bản sao runtime của mọi kiểu T: việc chuyên biệt hóa trong ngữ cảnh này gắn với quy tắc erasure và bridge.

**Không phải mọi generic method đều có bridge**; compiler chỉ tạo khi cần giữ đúng quan hệ method ở bytecode. Ví dụ chỉ khai báo List<String> hoặc một generic method không cần override với descriptor khác không tự động tạo bridge tương ứng.

## 4. Ví dụ Java 17 hoàn chỉnh: generic override và Reflection

Tạo cấu trúc:

~~~text
bridge-lab/
├── src/
│   └── demo/
│       └── bridge/
│           ├── Processor.java
│           ├── StringProcessor.java
│           └── BridgeDemo.java
└── out/                      # Sẽ tạo trước bước compile
~~~

### Tệp src/demo/bridge/Processor.java

~~~java
package demo.bridge;

public class Processor<T> {
    public T process(T input) {
        return input;
    }
}
~~~

### Tệp src/demo/bridge/StringProcessor.java

~~~java
package demo.bridge;

import java.util.Locale;

public final class StringProcessor extends Processor<String> {
    @Override
    public String process(String input) {
        return input.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

Phương thức strip() có từ Java 11; toUpperCase(Locale.ROOT) giúp phép chuẩn hóa chữ hoa nhất quán với ví dụ. @Override là annotation xác nhận quan hệ override ở mức source; nó không trực tiếp yêu cầu javac sinh bridge.

### Tệp src/demo/bridge/BridgeDemo.java

~~~java
package demo.bridge;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public final class BridgeDemo {
    private BridgeDemo() {
    }

    public static void main(String[] args) {
        Processor<String> processor = new StringProcessor();
        System.out.println("Call: " + processor.process("  java  "));

        Method[] methods = StringProcessor.class.getDeclaredMethods();
        Arrays.sort(methods,
                Comparator.comparing(m ->
                        m.getParameterTypes()[0].getSimpleName()));

        for (Method method : methods) {
            if (method.getName().equals("process")) {
                System.out.printf(
                        "%s -> %s | bridge=%s | synthetic=%s%n",
                        method.getParameterTypes()[0].getSimpleName(),
                        method.getReturnType().getSimpleName(),
                        method.isBridge(),
                        method.isSynthetic());
            }
        }
    }
}
~~~

Đây là ba tệp nguồn đầy đủ, mỗi public class nằm trong tệp cùng tên. Reflection getDeclaredMethods() lấy method thuộc riêng class StringProcessor, bao gồm cả method do compiler sinh. Arrays.sort cố định thứ tự Object rồi String; thứ tự mặc định của mảng Reflection **không được bảo đảm**. Điều kiện ví dụ chỉ dùng các method process đều có một tham số nên getParameterTypes()[0] hợp lệ.

### Biên dịch từ thư mục gốc bridge-lab

Trên Bash:

~~~bash
mkdir -p out
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Sau khi tạo out, thực hiện:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/bridge/Processor.java src/demo/bridge/StringProcessor.java src/demo/bridge/BridgeDemo.java
java -cp out demo.bridge.BridgeDemo
~~~

**Stdout chính xác trên JDK 17+:**

~~~text
Call: JAVA
Object -> Object | bridge=true | synthetic=true
String -> String | bridge=false | synthetic=false
~~~

Giải thích từng dòng:

1. Qua biến kiểu Processor<String>, gọi process vẫn dùng implementation StringProcessor, kết quả đã strip và viết hoa thành JAVA.
2. Method process(Object) có cờ bridge=true và synthetic=true: đây là method do javac thêm vào class file.
3. Method process(String) có hai cờ false: đây là method mà tác giả viết trong StringProcessor.java.

Trong source của StringProcessor chỉ có **một** khai báo process(String); không nên gọi method thứ hai là một overload chủ động của lập trình viên.

## 5. Đọc đầu ra javap từng cấp

Từ gốc bridge-lab, chạy:

~~~sh
javap -classpath out -p demo.bridge.StringProcessor
~~~

Các dòng đáng chú ý:

~~~text
public final class demo.bridge.StringProcessor extends demo.bridge.Processor<java.lang.String> {
  public demo.bridge.StringProcessor();
  public java.lang.String process(java.lang.String);
  public java.lang.Object process(java.lang.Object);
}
~~~

Lệnh này cho thấy hai method cùng tên trong class file nhưng chưa nêu đầy đủ cờ. Muốn biết descriptor và flags:

~~~sh
javap -classpath out -v -p demo.bridge.StringProcessor
~~~

Tìm đoạn tương ứng bridge (phần dưới là trích dẫn rút gọn có chủ đích; constant-pool indexes, offsets có thể khác nhau):

~~~text
public java.lang.Object process(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (...) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
  Code:
    ...
    checkcast     ... // class java/lang/String
    invokevirtual ... // Method process:(Ljava/lang/String;)Ljava/lang/String;
    areturn
~~~

Các instruction quan trọng:

- **checkcast**: xác minh tham số Object có thể được dùng như String khi chuyển tiếp. Nếu không tương thích, ClassCastException có thể xảy ra lúc chạy.
- **invokevirtual**: gọi method implementation process(String) của lớp con.
- **areturn**: trả tham chiếu kết quả về caller theo descriptor Object của bridge.

Trong bản class file được tạo bởi javac ở ví dụ này, bridge được đánh dấu đồng thời ACC_BRIDGE và ACC_SYNTHETIC. Flags là bằng chứng rõ ràng hơn việc suy đoán từ tên method. Javap -p giúp thấy cả các method không public; javap -v giúp quan sát code và metadata.

So sánh với lớp cha:

~~~sh
javap -classpath out -p demo.bridge.Processor
javap -classpath out -v -p demo.bridge.Processor
~~~

Trong phần hiển thị dễ đọc, javap có thể trình bày chữ ký generic T, nhưng descriptor thực tế của Processor.process là Object -> Object. Metadata Signature lưu thông tin generic phục vụ công cụ, không thay đổi descriptor dùng cho JVM dispatch.

## 6. Hai đường gọi và vai trò runtime của bridge

Xét đoạn minh họa đặt trong một phương thức hợp lệ:

~~~java
Processor<String> parentView = new StringProcessor();
StringProcessor childView = new StringProcessor();

String first = parentView.process(" one ");
String second = childView.process(" two ");
~~~

Compiler có thể mã hóa lời gọi qua parentView theo descriptor của Processor.process(Object):Object, rồi cast kết quả về String phù hợp kiểu của biểu thức nguồn. Vì vậy JVM cần bridge trong StringProcessor để dispatch đến typed process(String).

Với childView, compiler thấy trực tiếp method process(String):String và có thể gọi descriptor chuyên biệt. Hai cách gọi vẫn cùng ngữ nghĩa nghiệp vụ.

Bridge không phải một API để tự gọi trực tiếp trong source. Nó là chi tiết triển khai giúp hợp đồng override đúng cả sau khi generics bị erase.

### Thí nghiệm có chủ đích: raw type gây ClassCastException

Đoạn sau là một **phương thức minh họa không an toàn**, không phải class độc lập:

~~~java
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafeCall() {
    Processor raw = new StringProcessor();
    raw.process(123);
}
~~~

Do raw type loại bỏ một phần kiểm tra generic lúc biên dịch, compiler cho phép lời gọi với Integer theo descriptor nhận Object (thường phát sinh cảnh báo raw/unchecked nếu không suppress). Tại runtime, bridge StringProcessor.process(Object) phải cast Integer sang String, dẫn tới **ClassCastException**. Đây là ví dụ hữu ích để hiểu checkcast trong bridge, nhưng không phải cách lập trình nên dùng.

Không nên hiểu rằng compiler chèn bridge để “tự sửa” kiểu tham số sai. Bridge bảo toàn dispatch và kiểm tra runtime cần thiết; type safety của generics vẫn phụ thuộc việc dùng đúng các kiểu nguồn thay vì raw.

## 7. Covariant return cũng có thể tạo bridge

Generic erasure không phải nguyên nhân duy nhất. Java cho phép override trả về một **kiểu tham chiếu con** so với kiểu trả về ở lớp cha; đó là covariant return type. Nhưng descriptor JVM bao gồm cả return type, nên compiler có thể sinh bridge để giữ tương thích với lời gọi theo descriptor cũ.

Tạo tệp **src/demo/covariant/CovariantDemo.java** với toàn bộ nội dung:

~~~java
package demo.covariant;

class NumberSource {
    Number read() {
        return 5;
    }
}

class IntegerSource extends NumberSource {
    @Override
    Integer read() {
        return 7;
    }
}

public final class CovariantDemo {
    public static void main(String[] args) {
        NumberSource source = new IntegerSource();
        System.out.println("Value: " + source.read());
    }
}
~~~

Ba class ở cùng một file; chỉ có CovariantDemo là public, nên đặt tên CovariantDemo.java là hợp lệ.

Từ gốc dự án có sẵn out, biên dịch và chạy:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/covariant/CovariantDemo.java
java -cp out demo.covariant.CovariantDemo
~~~

**Stdout:**

~~~text
Value: 7
~~~

Kiểm tra bytecode:

~~~sh
javap -classpath out -p demo.covariant.IntegerSource
javap -classpath out -v -p demo.covariant.IntegerSource
~~~

Method đáng chú ý trong class IntegerSource:

~~~text
java.lang.Integer read();
java.lang.Number read();
~~~

Method Integer read() là override do người viết khai báo. Method Number read() là bridge do javac sinh, mang cờ **ACC_BRIDGE, ACC_SYNTHETIC** trong đầu ra ví dụ. Hai method cùng tên, không có tham số, nhưng **khác kiểu trả về ở descriptor JVM**. Chỉ viết hai method như thế trong Java source sẽ không hợp lệ vì Java không cho overload bằng return type.

Phân biệt với bridge do generics: trong trường hợp covariant return này, tham số không bị erase từ T thành Object; vấn đề cần nối nằm ở kiểu trả về Number so với Integer.

## 8. Synthetic member rộng hơn bridge method

Synthetic member là thành phần được đánh dấu bởi metadata class file. Một số thành phần do compiler sinh để triển khai lambda, enum, lớp lồng nhau hoặc cấu trúc nguồn khác có thể là synthetic; số lượng, tên và dạng bytecode phụ thuộc compiler/JDK.

### Ví dụ lambda: synthetic nhưng không bridge

Tạo **src/demo/synthetic/LambdaDemo.java**:

~~~java
package demo.synthetic;

public final class LambdaDemo {
    private LambdaDemo() {
    }

    public static void main(String[] args) {
        Runnable task = () -> System.out.println("task");
        task.run();
    }
}
~~~

Biên dịch và chạy với out đã được tạo:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/synthetic/LambdaDemo.java
java -cp out demo.synthetic.LambdaDemo
javap -classpath out -v -p demo.synthetic.LambdaDemo
~~~

**Stdout:**

~~~text
task
~~~

Với javac của bài thực hành, javap -p hiển thị helper tên dạng **lambda$main$0** và javap -v đánh dấu helper này **ACC_SYNTHETIC** nhưng không phải ACC_BRIDGE. Đây là method phục vụ phần thân lambda; nó không tồn tại vì cần nối một method override với descriptor khác.

Với cơ chế lambda hiện đại, compiler thường dùng **invokedynamic** và bootstrap liên quan LambdaMetafactory. Không nên giả định mỗi lambda bắt buộc tạo một file class cố định có tên dự đoán được. Tên helper như lambda$main$0 là **chi tiết compiler**, không phải tên API để code nghiệp vụ phụ thuộc.

### Những trường hợp khác

- **Enum**: compiler cung cấp các method như values() và valueOf(String). Nhưng đừng suy luận mọi method do compiler cung cấp đều mang cờ synthetic. Javac còn có thể tạo field nội bộ lưu mảng giá trị enum, đánh dấu synthetic; tên field thường thấy như $VALUES không phải hợp đồng ngôn ngữ.
- **Nested classes**: compiler cũ có thể tạo helper access$... để vượt qua một số ranh giới private. Từ Java 11, cơ chế **nestmates** giúp nhiều truy cập được biểu diễn trực tiếp ở JVM, nên cùng source có thể không còn helper đó.
- **Các công cụ biến đổi bytecode**: thư viện instrumentation, proxy, AOP hoặc code generator có thể tạo thành phần riêng. Muốn biết chính xác, đọc class file thực tế và metadata; không áp một danh sách tên synthetic cố định cho tất cả compiler.

**Không phải mọi thành phần compiler tự sinh đều có cờ ACC_SYNTHETIC.** Có những method do compiler tạo để cung cấp API Java có chủ đích. Và không phải mọi synthetic method có cờ ACC_BRIDGE. Đây là phân biệt quan trọng nhất khi đọc một class file có nhiều method hơn source.

## 9. Phân biệt các khái niệm gần nhau

| Khái niệm | Bản chất | Dấu hiệu |
| --- | --- | --- |
| Overload | Cùng tên, tham số khác theo quy tắc Java | Có thể khai báo trong source |
| Override | Lớp con thay thế implementation method kế thừa | Có thể kiểm tra bằng @Override |
| Generic type erasure | Loại/thay kiểu tham số generic trong biểu diễn runtime | Descriptor Object hoặc upper bound |
| Bridge method | Chuyển tiếp lời gọi để giữ đúng overriding tại bytecode | ACC_BRIDGE, thường ACC_SYNTHETIC |
| Synthetic member | Thành phần được đánh dấu sinh bởi compiler | ACC_SYNTHETIC hoặc metadata liên quan |
| Covariant return | Override trả về kiểu tham chiếu cụ thể hơn | Có thể cần bridge đổi return descriptor |
| Helper bình thường | Method do người viết tạo để chia logic | Không tự động synthetic |
| Lambda helper | Một dạng chuyển đổi mã cho thân lambda | Có thể synthetic, không phải bridge |

Các điểm không nên nhầm:

- Dùng generics **không có nghĩa mọi class generic đều sinh bridge**.
- Dùng @Override **không tự động tạo bridge**; nó xác nhận quan hệ overriding theo ngôn ngữ.
- Một method bridge thường là synthetic với javac trong các ví dụ, nhưng một synthetic helper không nhất thiết là bridge.
- Method có flag synthetic vẫn có thể cần cho runtime. **Synthetic không có nghĩa có thể xóa an toàn**.
- Bytecode có thể chứa hai descriptor khác kiểu trả về ngay cả khi Java source không cho phép bạn viết hai overload như vậy.

## 10. Reflection: nhận diện method do compiler sinh

Java Reflection có hai method quan trọng:

~~~java
boolean bridge = method.isBridge();
boolean synthetic = method.isSynthetic();
~~~

Các API này đọc thông tin về method thực sự được class loader nạp. Để kiểm tra method trực tiếp trong class, dùng **Class.getDeclaredMethods()**. Nó trả cả public/private method khai báo trong class file, kể cả bridge/synthetic nếu có; nó không tổng hợp toàn bộ inherited methods.

Cũng có **Class.getMethods()** để lấy các public method có thể truy cập, bao gồm public inherited methods. Nếu đang tìm một helper private hoặc tất cả method do compiler thêm trong một class cụ thể, getDeclaredMethods() là lựa chọn phù hợp hơn.

Các lưu ý kỹ thuật:

1. Không dựa vào thứ tự của Method[]; cần output ổn định thì sort.
2. Không sử dụng riêng method name để phân biệt bridge. Hai method có thể cùng tên; hãy xem kiểu tham số, kiểu trả về và cờ.
3. isSynthetic() không tự cho biết **vì sao** compiler sinh method; cần xem bytecode.
4. Với các loại member khác, có Field.isSynthetic(), Constructor.isSynthetic(), Class.isSynthetic() khi phù hợp; không phải field/constructor nào do compiler đụng tới cũng synthetic.
5. Reflection và javap giải quyết hai câu hỏi bổ trợ: Reflection cho biết member runtime được nhìn thấy ra sao; javap -v cho biết descriptor, flags và instruction của class file.

### Framework quét method cần làm gì?

Một framework dùng Reflection để khám phá endpoint, serializer, AOP advice hoặc method handler có thể gặp bridge và method nguồn cùng lúc. Nếu đăng ký mỗi entry thành một hành vi nghiệp vụ độc lập, có nguy cơ **trùng method**, sai kiểu tham số hoặc xử lý hai lần.

Giải pháp phụ thuộc framework: thường cần nhận biết bridge, đối chiếu declaration gốc và chọn method biểu diễn hợp đồng API cần công khai. Tuy nhiên **không nên loại bỏ toàn bộ synthetic khỏi mọi tác vụ**; khi phân tích JVM dispatch hay bytecode, bridge là một phần thiết yếu của đường gọi.

## 11. Tác động đến nhị phân và lúc nâng cấp thư viện

Sau biên dịch, client bytecode lưu các tham chiếu method có tên, lớp đích và descriptor. Khi nâng cấp thư viện, thay đổi generic hierarchy, generic bound, covariant return hoặc cách override có thể làm thay đổi các method/compiler bridge được sinh.

Vì vậy cần tách ba câu hỏi:

1. **Source compatibility**: mã nguồn client còn biên dịch được với API mới không?
2. **Binary compatibility**: client class đã biên dịch cũ còn liên kết được với class mới không?
3. **Behavioral compatibility**: dispatch và cast tại runtime còn trả kết quả đúng không?

Ví dụ Processor/StringProcessor cho thấy compiler cần bridge để lời gọi vào process(Object):Object qua kiểu cha có thể thực thi typed process(String):String ở lớp con.

Không nên tự xóa bridge khi tối ưu bytecode hoặc viết công cụ instrumentation. Một bộ class/JAR không tương thích có thể dẫn đến dispatch sai hoặc lỗi liên kết như AbstractMethodError hoặc NoSuchMethodError trong những cấu hình cụ thể. Không phải cứ xóa bridge là chắc chắn nhận cùng một loại lỗi: kết quả phụ thuộc descriptor, class hierarchy và bytecode caller.

Trong dự án lớn:

- Giữ các artifact được build nhất quán với nhau.
- Khi thay API generic công khai, kiểm tra cả source và binary compatibility.
- Khi đọc bytecode đã qua proxy/instrumentation, xác minh flags thực thay vì suy đoán theo compiler nguồn.
- Không phụ thuộc vào tên helper synthetic như lambda$main$0 hoặc $VALUES trong business logic.
- Không trực tiếp gọi bridge bằng Reflection như một con đường API chính thức nếu không có nhu cầu công cụ rõ ràng.

## 12. Quy trình điều tra method lạ trong .class

1. **Xác nhận đúng artifact**: tìm file .class/JAR đang được ứng dụng thực sự chạy; tránh đọc nhầm bản build cũ.
2. **Liệt kê method**: dùng javap -classpath out -p package.Class.
3. **Xem descriptor**: dùng javap -classpath out -v -p package.Class, tìm descriptor, flags, Signature và Code.
4. **Đối chiếu source**: xem class cha/interface, generic bound, override và return type.
5. **Đọc hướng delegate**: bridge có thể cast, sau đó gọi method chuyên biệt; không phải mọi bridge đều có cùng instruction.
6. **Xác nhận bằng Reflection**: Method.isBridge()/isSynthetic(), tham số, kiểu trả về.
7. **Thử dynamic dispatch**: gọi cùng đối tượng qua kiểu cha và kiểu con rồi đối chiếu hành vi.

| Quan sát | Kết luận sai hay gặp | Cách xác minh |
| --- | --- | --- |
| Javap thấy thêm process(Object) | Tác giả đã viết overload Object | Xem source, ACC_BRIDGE và Code |
| Có generic | Chắc chắn có bridge | Kiểm tra có override cần nối descriptor không |
| Method được đánh dấu synthetic | Có thể xóa mà không ảnh hưởng runtime | Xem nó có phục vụ dispatch/chuyển đổi mã không |
| Không thấy access$000 | Không có truy cập private giữa nested class | Xem nestmates và compiler đang dùng |
| getDeclaredMethods() có hai method cùng tên | Reflection bị lỗi | Kiểm tra descriptor và bridge |
| Java source chỉ có process(String) | Bytecode cũng chỉ có một method | Dùng javap -p/-v |
| Covariant return không có generic | Không thể có bridge | Kiểm tra kiểu trả về trong descriptor |
| Thấy lambda$... trong javap | Tên có thể dùng như public API lâu dài | Đây là chi tiết triển khai có thể đổi |

## 13. Bài tập luyện tập

**Bài 1:** Chạy BridgeDemo. Vì sao biến kiểu Processor<String> vẫn gọi đúng StringProcessor.process(String)? Trả lời bằng descriptor của method gốc và bridge.

**Bài 2:** Dùng javap -v để tìm ACC_BRIDGE, ACC_SYNTHETIC trong StringProcessor. Xác định checkcast và invokevirtual dẫn tới process(String).

**Bài 3:** Bỏ Arrays.sort khỏi BridgeDemo rồi chạy lại. Thứ tự Reflection được Java cam kết hay không? Đáp án: không.

**Bài 4:** Thêm IntegerProcessor extends Processor<Integer>, override Integer process(Integer). Dự đoán descriptor bridge còn nhận Object không khi type variable T không bound; kiểm tra bằng javap.

**Bài 5:** Biên dịch CovariantDemo.java và tìm bridge trả Number. Giải thích tại sao hai method read() khác return descriptor dù source không có generics.

**Bài 6:** Biên dịch LambdaDemo.java. Tìm synthetic method do javac tạo cho lambda, kiểm tra nó không có ACC_BRIDGE. Tên helper có phải một API được Java chuẩn hóa không?

**Bài 7:** Thử gọi raw Processor với Integer vào StringProcessor trong bản thực hành riêng. Dự đoán ClassCastException tại cast nào. Rút ra vì sao tránh raw type.

**Bài 8:** Viết một bảng bốn cột cho hai method StringProcessor.process: khai báo nguồn, JVM descriptor, ACC_BRIDGE, ACC_SYNTHETIC. Điền được bảng mà không đoán tên helper là dấu hiệu bạn đã hiểu.

## 14. Checklist kiến thức

- Phân biệt Java source signature với JVM descriptor.
- Giải thích T không bound bị erase thành Object.
- Hiểu process(String) là method nguồn, process(Object) là bridge do javac tạo.
- Tự biên dịch/chạy được ví dụ và quan sát đúng Reflection output.
- Đọc ACC_BRIDGE, ACC_SYNTHETIC và instruction qua javap -v.
- Hiểu covariant return cũng có thể tạo bridge.
- Thấy synthetic lambda helper không phải bridge.
- Biết không phải mọi thứ compiler sinh đều là synthetic và không phải mọi synthetic là bridge.
- Biết bridge có ý nghĩa với đa hình, binary compatibility và công cụ Reflection.

### Đọc sâu

- **Java Language Specification (JLS)**: *Type Erasure*, *Method Signature*, *Overriding* và *Return-Type-Substitutability*.
- **Java Virtual Machine Specification (JVMS)**: method descriptor, định dạng method_info, ACC_BRIDGE, ACC_SYNTHETIC, Signature và Code.
- **Reflection API**: java.lang.reflect.Method.isBridge(), isSynthetic() và Class.getDeclaredMethods().

Một bridge method là adapter bytecode cho các lời gọi đa hình có descriptor cần duy trì sau biến đổi của compiler. Synthetic member là một khái niệm rộng hơn về dấu hiệu compiler-generated. Khi hiểu cả **mã nguồn, descriptor, flags và lệnh bytecode**, bạn có thể giải thích chính xác vì sao đầu ra biên dịch xuất hiện những thành phần không viết trong source.
