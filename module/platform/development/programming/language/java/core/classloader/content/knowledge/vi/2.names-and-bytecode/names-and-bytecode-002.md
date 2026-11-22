# Tên lớp lồng, lớp cục bộ và lớp vô danh trong Java

## 1. Vì sao cần phân biệt lớp thành viên, cục bộ và vô danh?

Một lớp thành viên có thể được viết là `Outer.Inner` trong Java nhưng mang binary name `Outer$Inner` ở class file. Với **lớp cục bộ** và **lớp vô danh**, compiler còn tạo thành phần đánh số trong tên; chỉnh sửa mã hoặc đổi compiler có thể làm phần này thay đổi. Chỉ nhìn chuỗi tên `.class` không đủ xác định loại lớp, quan hệ bao ngoài hay cách khởi tạo.

Bài này phân biệt thành viên static, inner member, local class và anonymous class bằng khai báo Java, API Reflection và metadata bytecode; sau đó kiểm tra cách bắt biến, tạo instance và ranh giới với lambda.

## 2. Phân loại kiểu khai báo lồng nhau

Xét lớp ngoài Outer:

~~~java
public class Outer {
    static class StaticMember { }  // Lớp thành viên static

    class InnerMember { }           // Lớp thành viên không static

    void work() {
        class LocalTask { }         // Lớp cục bộ có tên, trong thân phương thức

        Runnable task = new Runnable() { // Lớp vô danh
            @Override
            public void run() { }
        };
    }
}
~~~

- **Lớp thành viên static (static nested class):** khai báo trực tiếp trong thân một kiểu với từ khóa static. Là kiểu thành viên của Outer, không gắn với một đối tượng Outer chỉ vì cách khai báo này. Ví dụ tạo đối tượng: new Outer.StaticMember() nếu quyền truy cập cho phép.
- **Lớp thành viên không static (inner member class):** khai báo trực tiếp trong kiểu bao ngoài và không có static. Một đối tượng InnerMember thường mang liên kết với đối tượng Outer bao ngoài; ví dụ tạo trong ngữ cảnh phù hợp: outer.new InnerMember().
- **Lớp cục bộ (local class):** khai báo có tên trong một khối, chẳng hạn thân phương thức, constructor hoặc khối khởi tạo. Phạm vi tên theo quy tắc lexical scope của nơi khai báo; không thể tham chiếu đơn giản từ bên ngoài phạm vi đó như một lớp thành viên.
- **Lớp vô danh (anonymous class):** khai báo và tạo đối tượng qua biểu thức new với thân lớp; không có tên lớp do người lập trình đặt. Ví dụ new Runnable() { ... } tạo một lớp triển khai Runnable; new SomeBase() { ... } tạo lớp con của SomeBase. Không dùng anonymous class để khai báo một kiểu độc lập có thể gọi tên trong mã nguồn.

Theo thuật ngữ JLS, **nested class** bao gồm lớp thành viên, lớp cục bộ và lớp vô danh. **Inner class** là các lớp lồng không được khai báo static theo các điều kiện của ngôn ngữ, bao gồm inner member, local class và anonymous class trong trường hợp thông thường. Đừng đồng nhất mọi nested class với inner member class.

## 3. Bốn kiểu tên cần phân biệt

| Khái niệm | Dùng để làm gì? | Ví dụ với lớp thành viên Outer.InnerMember |
| --- | --- | --- |
| **Simple name** | Tên ngắn không kèm kiểu bao ngoài; lấy bằng Class.getSimpleName() | InnerMember |
| **Canonical name** | Tên chuẩn tắc theo dạng tên Java khi kiểu có canonical name; lấy bằng Class.getCanonicalName() | Outer.InnerMember |
| **Binary name** | Tên định danh kiểu trong cơ chế liên kết và tải lớp; Class.getName() trả tên này với các lớp thường | Outer$InnerMember |
| **JVM internal name** | Tên trong cấu trúc class file/constant pool, phân tách package bằng dấu / | demo/Outer$InnerMember |

Nếu Outer nằm trong package demo, tên chuẩn tắc là demo.Outer.InnerMember và tên nhị phân là demo.Outer$InnerMember. Ký tự $ nối tên lớp bao ngoài với lớp thành viên trong **binary name**; dấu chấm vẫn là cú pháp được viết trong Java source.

Tên file do javac thường tạo ra tương ứng với binary name, thay các dấu chấm package bằng đường dẫn thư mục: demo/Outer$InnerMember.class. Với kiểu reference, JVM descriptor dùng dạng Ldemo/Outer$InnerMember; (có dấu chấm phẩy cuối). **Tên class file, binary name và descriptor là các khái niệm liên quan nhưng không thể hoán đổi cú pháp.**

Lưu ý: dấu $ cũng có thể xuất hiện hợp lệ trong tên định danh do lập trình viên đặt. Vì vậy không được tự tách một chuỗi chỉ dựa vào mọi ký tự $ rồi khẳng định cấu trúc nguồn. Cũng không được dùng tên hiển thị từ toString() làm giao thức định danh lớp.

## 4. Cách javac đặt tên cho từng dạng

Giả sử lớp ngoài là demo.Outer. Bảng dưới minh họa cách đặt tên thường gặp khi biên dịch bằng javac; phần số do trình biên dịch quyết định, không phải tên nguồn ổn định.

| Dạng lớp | Biểu thức/khai báo trong source | Binary name minh họa | Canonical name | Simple name |
| --- | --- | --- | --- | --- |
| Lớp trên cùng (top-level) | class Outer | demo.Outer | demo.Outer | Outer |
| Thành viên static | static class StaticMember | demo.Outer$StaticMember | demo.Outer.StaticMember | StaticMember |
| Thành viên không static | class InnerMember | demo.Outer$InnerMember | demo.Outer.InnerMember | InnerMember |
| Cục bộ có tên | class LocalTask trong phương thức | demo.Outer$1LocalTask | null | LocalTask |
| Vô danh | new Runnable() { ... } | demo.Outer$1 | null | chuỗi rỗng |

**Nhận xét quan trọng:**

1. Lớp thành viên có tên được ghép với lớp bao ngoài bằng dấu $ trong tên nhị phân; tên chuẩn tắc của lớp thành viên vẫn dùng dấu chấm. Tính static không quyết định sự có mặt của dấu $.
2. Lớp cục bộ có **simple name** là tên đã viết (LocalTask), nhưng **không có canonical name**. Tên nhị phân chứa phần số giữa tên lớp bao ngoài và tên cục bộ theo quy tắc JLS; ví dụ có thể là Outer$1LocalTask.
3. Lớp vô danh không có tên đơn giản trong source: Class.getSimpleName() trả chuỗi rỗng; Class.getCanonicalName() trả null. Binary name ví dụ Outer$1, Outer$2.
4. **Không dựa vào số 1, 2, 3 để suy ra thứ tự thực thi hay ý nghĩa nghiệp vụ.** Chỉnh sửa source, đổi phạm vi lồng nhau hoặc thay compiler có thể làm thay đổi tên phát sinh. Dữ liệu cấu trúc từ reflection và thuộc tính class file đáng tin hơn việc đoán bằng regex.
5. Với lớp cục bộ hoặc vô danh nằm sâu trong lớp lồng khác, tiền tố binary name có thể chứa nhiều dấu $. Tên phát sinh là hiện vật biên dịch, không nên ghi cứng làm API công khai, cấu hình dài hạn hay khóa lưu trữ.

## 5. Ví dụ Java 17+ chạy được: quan sát Reflection

Tạo file **ClassNameDemo.java** với toàn bộ mã sau (không cần package để lệnh chạy ngắn gọn):

~~~java
public class ClassNameDemo {
    static class StaticMember { }

    class InnerMember { }

    private static void inspect(String label, Class<?> type) {
        System.out.printf(
                "%s | simple='%s' | canonical=%s | member=%b | local=%b | anonymous=%b%n",
                label,
                type.getSimpleName(),
                type.getCanonicalName(),
                type.isMemberClass(),
                type.isLocalClass(),
                type.isAnonymousClass()
        );
    }

    private static void demonstrate() {
        class Local { }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() { }
        };

        inspect("static", StaticMember.class);
        inspect("inner", InnerMember.class);
        inspect("local", Local.class);
        inspect("anonymous", anonymous.getClass());
    }

    public static void main(String[] args) {
        demonstrate();
    }
}
~~~

Biên dịch tương thích Java 17 rồi chạy (máy cần JDK 17 trở lên):

~~~bash
javac --release 17 ClassNameDemo.java
java ClassNameDemo
~~~

**Stdout chính xác:**

~~~text
static | simple='StaticMember' | canonical=ClassNameDemo.StaticMember | member=true | local=false | anonymous=false
inner | simple='InnerMember' | canonical=ClassNameDemo.InnerMember | member=true | local=false | anonymous=false
local | simple='Local' | canonical=null | member=false | local=true | anonymous=false
anonymous | simple='' | canonical=null | member=false | local=false | anonymous=true
~~~

Chương trình không in phần số trong binary name, vì phần số đó không phù hợp làm kết quả cố định giữa các trường hợp biên dịch. Muốn xem tên nhị phân đang có ở máy mình, thêm lệnh **System.out.println(type.getName());** trong inspect; với javac bạn sẽ thấy các dạng như ClassNameDemo$StaticMember, ClassNameDemo$InnerMember, ClassNameDemo$1Local và ClassNameDemo$1 (con số cụ thể phụ thuộc kết quả biên dịch).

**Đọc kết quả:** cả static member và inner member trả isMemberClass() = true, nhưng một lớp member có static hay không cần kiểm tra modifier khi thực sự quan tâm. Local và anonymous đều không phải member class. Giá trị null của canonical name không có nghĩa lớp không có binary name hoặc không có class file.

## 6. Reflection: xác định quan hệ bao ngoài một cách có cấu trúc

Các API trên java.lang.Class giúp trả lời các câu hỏi khác nhau:

| API | Ý nghĩa | Đối với ví dụ trên |
| --- | --- | --- |
| getName() | Tên nhị phân cho lớp reference thông thường | ClassNameDemo$InnerMember; local/anonymous có tên do compiler phát sinh |
| getSimpleName() | Tên đơn giản, có thể rỗng | Local → Local; anonymous → "" |
| getCanonicalName() | Tên chuẩn tắc nếu tồn tại | Member → ClassNameDemo.Member; local/anonymous → null |
| isMemberClass() | Có được khai báo làm kiểu thành viên trực tiếp của kiểu khác? | true cho hai lớp thành viên |
| isLocalClass() | Là lớp cục bộ? | true cho Local |
| isAnonymousClass() | Là lớp vô danh? | true cho biểu thức new Runnable() { ... } |
| getDeclaringClass() | Kiểu khai báo thành viên này, nếu có | ClassNameDemo với member; null cho local/anonymous |
| getEnclosingClass() | Kiểu bao ngoài về mặt khai báo, nếu có | ClassNameDemo cho cả bốn dạng đang xét |
| getEnclosingMethod() | Phương thức chứa khai báo lớp local/anonymous, nếu có | demonstrate với Local và anonymous; null với hai member |

Nếu lớp local/anonymous được khai báo trong **constructor**, có thể xem getEnclosingConstructor() thay vì getEnclosingMethod(). Một lớp thành viên có enclosing class nhưng không có enclosing method. Class.getDeclaredClasses() trả các lớp/interface **thành viên được khai báo trực tiếp** bởi lớp đó, không liệt kê mọi local class và anonymous class có thể xuất hiện trong thân phương thức; đừng dùng nó để khẳng định đã tìm hết mọi file Outer$*.class.

Trường hợp cần phát hiện thành viên static, có thể dùng **java.lang.reflect.Modifier.isStatic(type.getModifiers())** cùng với isMemberClass(). Điều này phân biệt tường minh tính static của thành viên và việc lớp có một dấu $ trong binary name.

## 7. Lớp cục bộ và vô danh có thể bắt biến như thế nào?

Lớp local và anonymous có thể dùng các biến cục bộ và tham số từ phạm vi bao quanh nếu chúng là **final hoặc effectively final** (giá trị không bị gán lại sau khi được khởi tạo). Hành vi này giải thích vì sao bytecode của lớp phát sinh đôi khi có trường tổng hợp (synthetic field) để giữ giá trị đã bắt. Ngoài ra inner class khai báo trong ngữ cảnh instance có thể cần tham chiếu tới instance bao ngoài.

Ví dụ **CaptureDemo.java** độc lập:

~~~java
public class CaptureDemo {
    void demo() {
        int base = 10; // effectively final

        class LocalAdder {
            int add(int value) {
                return base + value;
            }
        }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println(base);
            }
        };

        System.out.println(new LocalAdder().add(5));
        anonymous.run();
    }

    public static void main(String[] args) {
        new CaptureDemo().demo();
    }
}
~~~

Chạy bằng **javac --release 17 CaptureDemo.java** rồi **java CaptureDemo**:

~~~text
15
10
~~~

Nếu thêm **base++** sau khi khởi tạo, lớp local và anonymous đang truy cập biến đó sẽ gây lỗi biên dịch vì base không còn effectively final. Tính ràng buộc này thuộc ngữ nghĩa của Java source; nó không được suy ra đơn thuần từ tên có $.

Một đối tượng của inner member class được tạo từ instance ngoài khác với đối tượng static member. Tuy nhiên không nên khẳng định rằng *mọi* file lớp lồng luôn có trường this$0 hoặc val$...: compiler và tối ưu có thể thay đổi biểu diễn, nhất là khi không cần giữ tham chiếu. Kiểm tra bytecode thực tế khi phân tích.

## 8. Từ source sang file .class: quan sát bằng javap

Sau khi biên dịch ClassNameDemo.java, thư mục đầu ra thường có các file dạng sau:

~~~text
ClassNameDemo.class
ClassNameDemo$StaticMember.class
ClassNameDemo$InnerMember.class
ClassNameDemo$1Local.class
ClassNameDemo$1.class
~~~

Đây là **minh họa cho đầu ra thường gặp của javac**, không phải hợp đồng rằng phần số luôn bằng 1 ở mọi phiên bản compiler hay sau mọi chỉnh sửa mã. Mỗi lớp local/anonymous dùng trong source có thể được biên dịch thành class file riêng. Không được hiểu rằng chỉ file ClassNameDemo.class mới chứa toàn bộ mã bytecode của tất cả các lớp lồng.

Quan sát cấu trúc class file:

~~~bash
javap -p -v ClassNameDemo
~~~

Bạn có thể thấy các thuộc tính **InnerClasses**, **NestMembers** hoặc thông tin lớp lồng liên quan. Khi dùng javap -v trên file của một lớp cục bộ hay vô danh, có thể thấy thêm **EnclosingMethod**. Các metadata này giúp JVM và reflection mô tả quan hệ khai báo.

- **InnerClasses** lưu mô tả các lớp được lồng vào nhau theo cấu trúc class file, gồm thông tin inner/outer và inner name khi áp dụng.
- **EnclosingMethod** có thể cho biết lớp local/anonymous được khai báo ở kiểu và phương thức/constructor nào.
- **NestHost/NestMembers** (cơ chế nestmates từ Java 11) hỗ trợ quan hệ truy cập private giữa các thành viên cùng nest ở cấp JVM. Đây là khái niệm kỹ thuật của JVM, không phải phép thay thế cho phân loại isLocalClass/isAnonymousClass.
- Các tên trường/hàm synthetic và chi tiết đánh số phụ thuộc compiler; tránh xây ứng dụng dựa trên một bố cục bytecode quan sát được ở một lần biên dịch.

Lưu ý khi đọc bằng PowerShell: tên file chứa dấu $ nên dùng dấu nháy đơn nếu truyền tên file cụ thể cho công cụ hoặc lệnh; trong nhiều shell dấu $ có thể bị diễn giải như biến.

## 9. ClassLoader, Class.forName và đường dẫn tài nguyên

Với lớp thành viên **demo.Outer.InnerMember**, ba chuỗi sau có ý nghĩa khác nhau:

~~~text
Tên trong Java source:          demo.Outer.InnerMember
Binary name dùng để tải lớp:     demo.Outer$InnerMember
Resource path của class file:    demo/Outer$InnerMember.class
~~~

**Class.forName("demo.Outer$InnerMember")** nhận tên nhị phân của lớp reference bình thường; **Class.forName("demo.Outer.InnerMember")** không tự hiểu dấu chấm cuối là lớp thành viên, nên thông thường sẽ dẫn tới ClassNotFoundException khi không tồn tại lớp có đúng binary name ấy. Với ClassLoader.loadClass, tên đầu vào cho lớp thông thường cũng là binary name, còn ClassLoader.getResource/getResourceAsStream sử dụng tên tài nguyên với dấu / như cấu trúc đường dẫn.

Ví dụ sau là **đoạn mã minh họa**, giả sử đã có lớp demo.Outer.InnerMember trên classpath:

~~~java
Class<?> member = Class.forName("demo.Outer$InnerMember");
String binary = member.getName(); // "demo.Outer$InnerMember"
String resource = "demo/Outer$InnerMember.class";
var stream = member.getClassLoader().getResourceAsStream(resource);
~~~

Nếu dùng **SomeClass.class.getResource("...")**, quy tắc tương đối so với package và dấu / đầu đường dẫn khác với **ClassLoader.getResource("...")**. Khi viết công cụ đọc class file, chọn đúng API và đúng đường dẫn để tránh tìm nhầm.

Đối với local/anonymous class, nếu biết binary name thực tế thì cơ chế tải lớp có thể xử lý tên đó, nhưng **không nên hardcode** các tên compiler sinh như Outer$1 hoặc Outer$2 làm định danh bền vững. Khi bạn đã có đối tượng, hãy dùng obj.getClass(); khi có Class<?> hãy dùng getName() để lấy giá trị thực tế. Đồng thời nhớ rằng danh tính một lớp runtime phụ thuộc **cả binary name và defining class loader**: hai loader khác nhau có thể định nghĩa hai Class<?> khác nhau từ cùng tên.

**Class.forName(String)** mặc định khởi tạo lớp được tìm theo quy tắc của API; tải/tra cứu lớp và việc tạo instance không phải cùng hành động. Inner member class có thể được load thành công, trong khi việc gọi constructor của nó vẫn đòi instance bao ngoài và tuân thủ quy tắc truy cập tương ứng.

## 10. Đừng nhầm anonymous class với lambda

Hai đoạn này đều cung cấp hành vi của Runnable, nhưng không cùng cơ chế ngôn ngữ:

~~~java
Runnable a = new Runnable() {
    @Override
    public void run() {
        System.out.println("A");
    }
};

Runnable b = () -> System.out.println("B");
~~~

**a** được tạo bởi một biểu thức khai báo lớp vô danh; Class.isAnonymousClass() trả true cho lớp sinh từ nó. **b** là biểu thức lambda; JVM/compiler có thể hiện thực bằng invokedynamic và lớp ẩn hoặc kỹ thuật khác, tùy phiên bản/triển khai. Không được coi lambda là một anonymous class có tên ổn định Outer$N hay suy diễn rằng b.getClass().isAnonymousClass() phải true. Các bytecode và tên lớp triển khai lambda không nên là thành phần API của ứng dụng.

Tương tự, method reference (ví dụ System.out::println) là biểu thức theo cơ chế lambda, không phải cú pháp khai báo anonymous class.

## 11. Lỗi thường gặp và cách kiểm tra

1. **Dùng dấu chấm để Class.forName tải inner member:** viết demo.Outer.InnerMember vì nhìn giống source. Hãy tra tên nhị phân thực bằng Class.getName(); với member class trong ví dụ là demo.Outer$InnerMember.
2. **Tin rằng mọi lớp có $ là anonymous:** member class, local class, tên định danh chứa $ đều có thể tạo binary name chứa $. Dùng isMemberClass/isLocalClass/isAnonymousClass cùng metadata.
3. **Cho rằng local class có canonical name vì có tên trong source:** getSimpleName() có thể là Local, nhưng getCanonicalName() trả null.
4. **Lấy thứ tự $1/$2 làm thứ tự chạy:** tên được tạo lúc biên dịch, không phản ánh số đối tượng đã tạo hay thứ tự thực thi.
5. **Xem getDeclaredClasses() là danh sách mọi lớp con trong file source:** API này phản ánh kiểu thành viên trực tiếp, không phải toàn bộ lớp local/anonymous nằm trong phương thức.
6. **Đánh đồng static member với inner member:** static nested không mặc nhiên cần instance Outer; inner member thường có ngữ cảnh instance Outer khi tạo.
7. **Phụ thuộc tên file synthetic hay trường this$0:** các chi tiết javac có thể biến đổi; chỉ dùng để debug/quan sát, không làm hợp đồng tương thích.
8. **Đổi anonymous class sang lambda rồi mong cùng reflection:** lambda có cơ chế triển khai khác, không bảo đảm tên Class, binary class file hay isAnonymousClass() giống nhau.
9. **Tự ghép đường dẫn resource từ canonical name:** với member, canonical name có dấu chấm ở ranh giới lớp; resource path phải phản ánh binary/internal name thực tế.

Một quy trình debug hiệu quả: (1) xác định khai báo trong source, (2) in Class.getName(), getSimpleName(), getCanonicalName() và các cờ phân loại, (3) kiểm tra thư mục output .class, (4) dùng javap -v xem metadata khi cần, (5) kiểm tra classpath và class loader nếu việc tải lớp thất bại. Các bước này giúp nối source với bytecode mà không phỏng đoán dựa vào phần số trong tên.

## 12. Tự kiểm tra kiến thức

**Tình huống A.** Outer có static class Entry và class Worker. Cả hai có thể cho Class.getName() chứa ký tự $? **Có.** Tính static ảnh hưởng quan hệ instance, không loại bỏ quy tắc binary name của lớp thành viên.

**Tình huống B.** Một local class tên Handler trả getSimpleName() bằng Handler. Có thể suy ra getCanonicalName() = Outer.Handler? **Không.** Local class không có canonical name dù có simple name.

**Tình huống C.** Bạn thấy file Outer$2.class. Có thể kết luận đó là đối tượng anonymous thứ hai được tạo lúc chạy? **Không.** Đây là tên hiện vật biên dịch; số không biểu diễn số đối tượng runtime. Xác minh bằng metadata/reflection.

**Tình huống D.** Có thể tải Outer$Inner bằng Class.forName nhưng không thể viết new Outer.Inner() nếu Inner là inner member và chưa có instance Outer? **Đúng.** Tải kiểu khác với cấp phát đối tượng; tạo inner member cần ngữ cảnh instance bao ngoài phù hợp.

**Tình huống E.** Dùng lambda thay new Runnable() { ... } có bảo đảm vẫn tạo file Outer$1.class? **Không.** Cơ chế dịch lambda và chi tiết lớp triển khai không phải anonymous class cố định.

## Tài liệu chuẩn để đối chiếu

- Java Language Specification, §8.1.3 — Inner Classes and Enclosing Instances: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3
- Java Language Specification, §13.1 — The Form of a Binary: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1
- Java Language Specification, §15.9.5 — Anonymous Class Declarations: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5
- Java 17 API, java.lang.Class: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- JVM Specification, §4.7 — Attributes of class file: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7
