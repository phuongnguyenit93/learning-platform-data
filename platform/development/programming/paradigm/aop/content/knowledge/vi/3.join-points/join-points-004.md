# Khởi tạo lớp, khởi tạo đối tượng và thứ tự thực thi trong AOP

## 1. Vì sao khởi tạo là một nhóm điểm can thiệp đặc biệt?

Trong Aspect-Oriented Programming (AOP), **join point** là một điểm có thể được nhận diện trong quá trình thực thi để áp dụng hành vi bổ sung (**advice**) theo một quy tắc chọn (**pointcut**). Ngoài phương thức thông thường, vòng đời lớp và đối tượng tạo ra một nhóm join point đáng chú ý: **khởi tạo lớp**, **lời gọi constructor**, **thực thi constructor**, **giai đoạn trước khởi tạo đối tượng** và **giai đoạn khởi tạo đối tượng**.

Sự khác biệt quan trọng là **class initialization** diễn ra theo vòng đời của một lớp đã được nạp bởi một class loader, còn **object initialization** diễn ra cho từng đối tượng. Một lớp có thể được khởi tạo một lần rồi tạo hàng triệu đối tượng; vì thế advice tại điểm khởi tạo lớp và advice quanh constructor có phạm vi, tần suất, trạng thái đối tượng và rủi ro rất khác nhau.

Hãy đặt ba câu hỏi trước khi thiết kế một aspect liên quan đến khởi tạo:

1. **Cần quan sát một lớp trở nên sẵn sàng hay mỗi lần tạo ra một đối tượng?**
2. **Cần chặn ở phía gọi lệnh tạo đối tượng, bên trong constructor hay ở toàn bộ giai đoạn khởi tạo?**
3. **Tại thời điểm advice chạy, dữ liệu của đối tượng đã hợp lệ chưa, và có thể truy cập an toàn không?**

Các tên join point và khả năng chọn bằng pointcut phụ thuộc ngôn ngữ/công cụ AOP. Một số bộ dệt bytecode hỗ trợ nhiều điểm vòng đời; một hệ thống chỉ chặn phương thức qua proxy có thể **không** cung cấp join point ở khối static initializer hay constructor. Bài này trình bày mô hình AOP nói chung, dùng Java 17 làm nền tảng để hiểu trình tự thực thi và nêu rõ giới hạn khi diễn giải theo công cụ cụ thể.

## 2. Bốn việc thường bị gọi nhầm là “khởi tạo”

Trước khi nói đến advice, cần phân biệt chính xác những hoạt động ở runtime Java:

| Hoạt động | Ý nghĩa | Phạm vi | Có đồng nghĩa với chạy constructor không? |
|---|---|---|---|
| **Loading (nạp lớp)** | Tìm/đọc hoặc tạo biểu diễn nhị phân để JVM có định nghĩa của lớp | Theo danh tính lớp và class loader | Không |
| **Linking (liên kết)** | Xác minh, chuẩn bị và có thể giải quyết các tham chiếu ký hiệu | Theo lớp | Không |
| **Class initialization** | Chạy các biểu thức khởi tạo trường static và khối static initializer của lớp theo quy tắc ngôn ngữ | Mỗi lần một lớp được khởi tạo trong danh tính runtime tương ứng | Không |
| **Object creation và initialization** | Cấp phát đối tượng, thiết lập giá trị mặc định, chạy chuỗi constructor và các bước khởi tạo instance | Theo từng đối tượng | Có liên quan trực tiếp |

**Loading không tự đồng nghĩa với initialization.** Một lớp có thể đã được nạp, chuẩn bị và chưa chạy phần static. Tương tự, **class initialization không tạo sẵn một instance**: việc gọi một phương thức static có thể khiến lớp được khởi tạo mà chưa gọi constructor nào.

Ngược lại, một biểu thức **new SomeClass(...)** thường yêu cầu lớp liên quan được khởi tạo trước khi đối tượng đầu tiên được tạo. Khi lớp đó đã khởi tạo xong, các lần tạo instance tiếp theo không chạy lại phần static chỉ vì gọi constructor lần nữa.

### 2.1. Danh tính lớp trong JVM

Từ góc độ JVM, tên lớp đơn thuần chưa đủ xác định một danh tính runtime: **tên nhị phân + class loader định nghĩa lớp** là yếu tố quan trọng. Hai class loader khác nhau có thể định nghĩa hai lớp có cùng tên; mỗi định nghĩa có quá trình khởi tạo riêng. Vì vậy, diễn đạt “static initializer chạy đúng một lần trên toàn ứng dụng” là thiếu chính xác trong hệ thống có nhiều class loader.

Cách diễn đạt chặt hơn: một lớp được khởi tạo theo quy tắc của JVM cho **mỗi danh tính lớp**; JVM đồng bộ hóa để không có hai luồng tùy ý cùng thực hiện khởi tạo một lớp như hai lần độc lập. Những lần truy cập sau khi khởi tạo thành công sử dụng trạng thái đã khởi tạo.

## 3. Class initialization: khi nào xảy ra và thứ tự nào?

Trong Java, các tình huống **active use** điển hình khiến lớp được khởi tạo trước khi tiếp tục gồm:

- Tạo một instance của lớp bằng **new**.
- Gọi một phương thức **static** được khai báo trong lớp.
- Gán hoặc đọc trường **static** được khai báo trong lớp, ngoại trừ một số truy cập hằng compile-time theo quy tắc ngôn ngữ.
- Một số thao tác phản xạ hay cơ chế runtime có ngữ nghĩa yêu cầu khởi tạo lớp.

Khi khởi tạo một lớp, JVM phải khởi tạo các superclass cần thiết trước; trong Java hiện đại, các superinterface khai báo default method cũng có thể nằm trong chuỗi khởi tạo bắt buộc. Sau đó, các biểu thức khởi tạo **static field** và **static initializer block** trong từng lớp chạy theo **thứ tự văn bản của lớp đó**, khi chúng được thực thi như một phần của quá trình khởi tạo.

Ví dụ lớp:

~~~java
class Counter {
    static int first = announce("static field");
    static {
        announce("static block");
    }

    static int announce(String message) {
        System.out.println(message);
        return 1;
    }
}
~~~

Đây là đoạn Java minh họa, chưa phải chương trình độc lập có **main**. Lần khởi tạo **Counter** sẽ in:

~~~text
static field
static block
~~~

Những lần gọi constructor của **Counter** về sau không tự chạy lại hai dòng static. Nếu chưa có hoạt động thực sự khiến lớp khởi tạo, chỉ việc một tên lớp xuất hiện trong mã nguồn không bảo đảm các dòng đã xuất hiện.

### 3.1. Khác biệt giữa “đã nạp” và “đã khởi tạo”

Chương trình Java 17 sau cho thấy tham chiếu hằng compile-time và việc nạp không yêu cầu khởi tạo ngay, trong khi đọc một trường static không phải hằng lại có thể kích hoạt initialization.

Tạo file **LoadingVsInitializing.java**:

~~~java
public class LoadingVsInitializing {
    static class Marker {
        static final int CONSTANT = 7;
        static int value = init();

        static int init() {
            System.out.println("Marker initialized");
            return 9;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("constant=" + Marker.CONSTANT);

        Class.forName(
                Marker.class.getName(),
                false,
                Marker.class.getClassLoader());

        System.out.println("loaded without initialization");
        System.out.println("value=" + Marker.value);
        System.out.println("again=" + Marker.value);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 LoadingVsInitializing.java
java LoadingVsInitializing
~~~

Stdout:

~~~text
constant=7
loaded without initialization
Marker initialized
value=9
again=9
~~~

Giải thích từng điểm:

1. **Marker.CONSTANT** là constant variable với giá trị biết được ở compile time; ở ví dụ này đọc hằng không bắt buộc khởi tạo **Marker**.
2. **Class.forName(name, false, loader)** yêu cầu tìm/nạp lớp theo API nhưng cờ **false** chỉ rõ không khởi tạo lớp chỉ bởi thao tác này. Biểu thức **Marker.class** cũng không buộc chạy static initialization của **Marker**.
3. Đọc **Marker.value** khiến lớp được khởi tạo; lệnh **init()** chạy rồi in đúng một lần.
4. Lần đọc **Marker.value** tiếp theo chỉ lấy giá trị 9 đã được tính.

Điểm cần nhớ với AOP: nếu pointcut nhắm vào **class initialization**, advice tương ứng không được suy diễn là chạy lúc lớp đơn thuần được nhắc tên, lúc reflection chỉ nạp lớp, hay mỗi lần đọc một trường. Nó gắn với **sự kiện khởi tạo lớp được công cụ hỗ trợ**, và sự kiện này có thời điểm xác định theo ngữ nghĩa JVM.

## 4. Object creation: từ cấp phát đến constructor hoàn tất

Đối với một biểu thức tạo đối tượng Java thông thường, nên hình dung các giai đoạn:

1. **Đánh giá biểu thức tạo và đối số** theo quy tắc đánh giá của Java; nếu việc đánh giá đối số thất bại, có thể chưa có đối tượng để khởi tạo.
2. **Đảm bảo lớp cần thiết đã được khởi tạo** trước khi thực sự sử dụng theo quy tắc JVM.
3. **Cấp phát vùng nhớ cho instance**, các trường instance nhận giá trị mặc định: số bằng 0, boolean bằng false, reference bằng null...
4. **Chạy chuỗi constructor** qua lời gọi **this(...)** hoặc **super(...)**; mỗi cấp trong hệ kế thừa thực hiện các bước khởi tạo thích hợp.
5. **Khởi tạo instance field và initializer block** trong lớp liên quan theo thứ tự văn bản tại vị trí được ngôn ngữ xác định.
6. **Thực thi thân constructor** sau các bước cần thiết; khi thành công, caller nhận reference đến đối tượng đã xây dựng xong theo lời gọi đó.

Bản mô tả trên là **sơ đồ sư phạm**, không phải danh sách instruction hay mốc join point phổ quát cho mọi weaver. Khi nghiên cứu thứ tự rất chi tiết, cần dựa vào đặc tả ngôn ngữ và quy ước của công cụ AOP cụ thể.

### 4.1. Khác biệt giữa cấp phát và khởi tạo thành công

Có một đối tượng đã được cấp phát không có nghĩa mọi bất biến của đối tượng đều đúng. Trong quá trình constructor, nhiều trường có thể còn giá trị mặc định; superclass đã chạy một phần, trong khi subclass chưa chạy khối khởi tạo riêng.

Đây là lý do advice chạy ở giai đoạn rất sớm **không nên tự ý truy cập trạng thái con**, gọi phương thức có thể bị override, hoặc đăng ký reference chưa hoàn tất vào một registry dùng chung.

Một phương thức có thể được dispatch động đến subclass dù constructor của superclass đang chạy. Nếu method bị override dựa vào trường chỉ được khởi tạo sau này, kết quả có thể bất ngờ. Weaving không loại bỏ quy tắc dispatch này.

### 4.2. Constructor chaining: this(...) khác super(...)

- **this(...)** chuyển sang constructor khác trong cùng lớp. Nó không có nghĩa tạo thêm một đối tượng khác.
- **super(...)** gọi constructor superclass trong quá trình xây dựng đối tượng hiện tại.
- Một lần **new Child()** có thể khiến nhiều constructor thực thi do chuỗi **this/super**, nhưng kết quả là **một instance Child**, trừ các thao tác cấp phát khác do mã chủ động thực hiện.

Ở Java 17, lời gọi constructor tường minh dạng **this(...)**/**super(...)** nằm ở vị trí được ngôn ngữ quy định. Khi tham gia một vòng đời tạo đối tượng có aspect, cần phân biệt **constructor được gọi từ biểu thức new** với các constructor được thực thi do chaining.

## 5. Ví dụ Java 17: thứ tự superclass, subclass, static và instance

Chương trình sau có hai lớp lồng nhau **Parent** và **Child**. Mỗi lớp có static field initializer, static block, instance field initializer, instance block và constructor. Lớp con có hai constructor nối nhau qua **this("default")**.

Tạo file **InitializationOrderDemo.java**:

~~~java
public class InitializationOrderDemo {
    static int traceValue(String event, int value) {
        System.out.println(event);
        return value;
    }

    static void trace(String event) {
        System.out.println(event);
    }

    static class Parent {
        static int parentStatic = traceValue("Parent.static field", 1);
        static {
            trace("Parent.static block");
        }

        int parentField = traceValue("Parent.instance field", 2);
        {
            trace("Parent.instance block");
        }

        Parent() {
            trace("Parent.constructor");
        }
    }

    static class Child extends Parent {
        static int childStatic = traceValue("Child.static field", 3);
        static {
            trace("Child.static block");
        }

        int childField = traceValue("Child.instance field", 4);
        {
            trace("Child.instance block");
        }

        Child() {
            this("default");
            trace("Child.constructor no-args");
        }

        Child(String source) {
            super();
            trace("Child.constructor arg=" + source);
        }
    }

    public static void main(String[] args) {
        trace("main: begin");
        trace("main: first object");
        new Child();
        trace("main: second object");
        new Child("explicit");
        trace("main: end");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 InitializationOrderDemo.java
java InitializationOrderDemo
~~~

Stdout chính xác:

~~~text
main: begin
main: first object
Parent.static field
Parent.static block
Child.static field
Child.static block
Parent.instance field
Parent.instance block
Parent.constructor
Child.instance field
Child.instance block
Child.constructor arg=default
Child.constructor no-args
main: second object
Parent.instance field
Parent.instance block
Parent.constructor
Child.instance field
Child.instance block
Child.constructor arg=explicit
main: end
~~~

Giải thích:

- Trước lần tạo **Child** đầu tiên, **Parent** được khởi tạo ở phần static rồi đến **Child**. Trong mỗi lớp, static field initializer và static block chạy theo thứ tự khai báo.
- Tạo **Child** gọi chuỗi constructor; phần instance của **Parent** chạy trước thân **Parent()**, rồi phần instance của **Child** chạy trước thân **Child(String)**.
- **Child()** ủy quyền cho **Child("default")**. Khi constructor nhận tham số kết thúc, điều khiển quay lại thân **Child()**, vì thế dòng **Child.constructor no-args** nằm sau dòng **Child.constructor arg=default**.
- Ở lần tạo thứ hai, các dòng static không lặp; các dòng instance và constructor lặp vì đó là **một đối tượng mới**.
- Kết quả này quan sát **quy tắc khởi tạo Java thuần**, chưa áp dụng aspect. Việc thêm advice có thể tạo thêm dòng hoặc tác dụng phụ tại một số giai đoạn, tùy bộ dệt và pointcut.

Sơ đồ của lần **new Child()** đầu:

~~~text
main: first object
    ↓
Class initialization
    Parent: static field → static block
    Child:  static field → static block
    ↓
Object initialization
    Parent: instance field → instance block → Parent()
    Child:  instance field → instance block → Child(String)
    Child:  phần thân còn lại của Child()
    ↓
Quay lại caller
~~~

Sơ đồ thứ hai:

~~~text
main: second object
    ↓
Không chạy lại static initializers đã hoàn tất
    ↓
Parent instance initialization + Parent()
    ↓
Child instance initialization + Child(String)
    ↓
Quay lại caller
~~~

Các log từ **traceValue** chỉ để nhìn rõ tiến trình; thứ tự thực sự còn phụ thuộc mã khác chạy trong initializer, constructor và superclass. Không nên suy ra rằng class initializer của mọi lớp trong toàn chương trình có một thứ tự toàn cục duy nhất, bất kể luồng và quan hệ phụ thuộc.

## 6. Các loại join point liên quan đến khởi tạo

Điều quan trọng nhất của bài là **mỗi loại join point mô tả một thời điểm khác nhau**. Trong các mô hình AOP có hỗ trợ điểm vòng đời chi tiết, có thể gặp các nhóm sau.

| Loại join point | Nhắm vào điều gì? | Điểm nhìn | Trạng thái đối tượng |
|---|---|---|---|
| **Class/static initialization** | Thực thi initializer ở mức lớp | Lớp đang được khởi tạo | Không gắn với một target instance cụ thể |
| **Constructor call** | Một lời gọi tạo đối tượng tại phía caller | Ranh giới nơi yêu cầu đối tượng mới | Có thể chỉ quan sát reference sau khi lời gọi tạo thành công |
| **Constructor execution** | Thực thi phần constructor cụ thể | Bên trong constructor được chọn | Đối tượng có thể chưa hoàn tất tất cả bước của subclass |
| **Object pre-initialization** | Khoảng trước phần khởi tạo instance của một lớp trong chuỗi xây dựng | Vòng đời đối tượng trước giai đoạn khởi tạo của lớp đó | Không được giả định trường instance đã hợp lệ |
| **Object initialization** | Giai đoạn thực hiện khởi tạo instance của lớp trong chuỗi constructor | Vòng đời object | Trạng thái thay đổi dần; chưa nhất thiết có đủ bất biến tại mọi điểm |
| **Field set/get** | Thao tác gán/đọc một trường, nếu mô hình hỗ trợ | Vị trí truy cập trường | Không đồng nhất với toàn bộ sự kiện constructor/initialization |

**Tính khả dụng phụ thuộc công cụ.** Một mô hình AOP chỉ intercept lời gọi interface thường không có đủ các join point trên. Một số ngôn ngữ/bộ dệt chi tiết còn phân biệt **constructor call** từ biểu thức tạo đối tượng với lời gọi **this/super** trong chuỗi constructor. Không được suy luận rằng mọi constructor chaining đều tạo thêm một constructor-call join point giống như **new**.

### 6.1. Constructor call: ai đang yêu cầu đối tượng?

Đây là góc nhìn từ mã caller, chẳng hạn:

~~~java
Child value = new Child();
~~~

Một pointcut nhắm vào lời gọi constructor có thể dùng để quan sát **vị trí yêu cầu đối tượng**, đối số tại biên gọi và kết quả reference khi lời gọi thành công, nếu ngôn ngữ AOP cung cấp những khả năng đó.

Khi có nhiều nơi gọi **new Child()**, một pointcut chọn call site có thể chỉ bao phủ một số caller hoặc một vùng mã xác định. Chặn một factory duy nhất cũng tương tự về góc nhìn: nó quan sát lời gọi qua factory, nhưng không tự bảo đảm quan sát lệnh **new** viết trực tiếp ở nơi khác.

**Thận trọng:** constructor call không phải là sự kiện static initialization và cũng không phải toàn bộ hoạt động bên trong constructor. Không nên mô tả nó là “phương thức constructor chuẩn bị chạy tại thân constructor” mà bỏ qua phía caller.

### 6.2. Constructor execution: constructor nào thực sự chạy?

Điểm thực thi constructor tập trung vào constructor được thực hiện. Trong một chuỗi **Child() → Child(String) → Parent()**, nhiều thân constructor có thể thực thi trên **cùng một đối tượng**.

Nếu advice đếm mỗi constructor execution là một đối tượng mới, số đếm có thể bị tăng sai. Đếm **số lượt thực thi constructor** không nhất thiết bằng **số instance được tạo**.

Mặt khác, advice gắn với execution cần biết thời điểm chính xác công cụ coi là “bắt đầu thực thi”: một số mô hình không bao quát các bước **this/super** theo cùng cách như phần thân constructor. Khi cần theo dõi toàn bộ vòng đời, chọn constructor execution đơn thuần có thể chưa đủ.

### 6.3. Object pre-initialization và object initialization

Hai khái niệm này cần được hiểu là **các giai đoạn vòng đời**, không phải tên khác của constructor call.

Một mô hình chi tiết như AspectJ phân biệt:

- **Pre-initialization:** khoảng trước khi phần khởi tạo instance của một lớp chạy, gắn với quá trình bắt đầu chuỗi constructor và bước chuẩn bị đi lên superclass.
- **Initialization:** khoảng khởi tạo một lớp trong quá trình tạo object, bao gồm các initializer instance và đường constructor liên quan sau khi superclass phù hợp đã được xử lý.

Những mô tả này phụ thuộc định nghĩa hình thức của từng ngôn ngữ AOP; ở ví dụ cụ thể, phạm vi một join point có thể chứa các join point khác. Nếu công cụ chỉ hỗ trợ method execution thì không thể tự lấy các điểm này bằng cách đổi tên pointcut.

**Không nên ghi một thứ tự advice tuyệt đối** như “pre-initialization → initialization → constructor execution” cho mọi công cụ hoặc mọi chuỗi constructor. Hãy xác minh thứ tự lồng nhau, advice precedence và phạm vi do công cụ định nghĩa.

### 6.4. Static initialization là join point của lớp, không phải của đối tượng

Khi khởi tạo lớp, có thể chưa có object nào được tạo. Vì vậy advice tại điểm này không thể mặc nhiên yêu cầu **this** của một target object để đọc trường instance.

Một bộ dệt cho phép can thiệp static initializer có thể nhận biết class đang khởi tạo; nhưng chính sự kiện đó không đồng nghĩa được gọi lại mỗi lần **new**. Nếu đặt logic kiểm toán “mỗi đơn hàng được tạo” tại static initialization của lớp đơn hàng, kết quả sẽ sai quy mô ngay từ thiết kế.

## 7. Cách đọc mô hình pointcut và advice tại các thời điểm khác nhau

Giả sử cần quan sát lớp **Child** và việc tạo instance của nó. Sau đây là **giả mã AOP độc lập công cụ**, không phải mã Java để biên dịch:

~~~text
aspect ConstructionTrace
    pointcut classReadyStage =
        static-initialization of Child

    pointcut callerCreatesChild =
        constructor-call Child(...)

    pointcut constructorsRunning =
        constructor-execution Child(...)

    before classReadyStage:
        report("initializing Child type")

    before callerCreatesChild:
        report("caller requests Child")

    after-returning callerCreatesChild:
        report("caller received Child")

    before constructorsRunning:
        report("a Child constructor executes")
end
~~~

Ý nghĩa logic:

- **static-initialization of Child** hướng đến khởi tạo lớp Child. Nếu lớp đã khởi tạo từ trước thì một lần tạo object sau không tạo thêm sự kiện khởi tạo lớp.
- **constructor-call Child(...)** quan sát biên caller yêu cầu Child, không có nghĩa quan sát mọi lời gọi **this/super** theo cùng kiểu.
- **constructor-execution Child(...)** có thể quan sát từng constructor được thực thi, kể cả các constructor trong chuỗi theo quy tắc của mô hình.
- **after-returning constructor-call** chỉ chạy khi thao tác tạo từ điểm caller quan sát trả về thành công; nếu constructor ném ngoại lệ, không có reference mới được trả về theo đường đó.

Giả mã này **không dự đoán chính xác thứ tự các dòng** nếu chưa xác định điểm weave, cách xử lý chuỗi constructor và precedence của các advice. Sự an toàn nằm ở chỗ phân biệt vai trò từng điểm; trong hệ thống thực, kiểm tra thứ tự bằng một chương trình nhỏ có thiết lập weaver cụ thể.

### 7.1. Đếm số đối tượng đúng chỗ

Bài toán: mỗi instance được tạo thành công cần tăng một counter đúng một lần.

- Counter gắn với **static initialization** chỉ tăng theo số lần lớp được khởi tạo, không theo số object.
- Counter gắn với **mọi constructor execution** có nguy cơ tính cả các bước **this(...)** hoặc nhiều constructor liên quan đến cùng object.
- Counter gắn với **constructor call từ những vị trí được chọn** có thể đếm thành công tại biên caller; nhưng có thể bỏ sót những lệnh tạo ngoài phạm vi pointcut.
- Một điểm theo dõi gắn với **hoàn tất khởi tạo object** được ngôn ngữ AOP hỗ trợ có thể thích hợp hơn; vẫn phải kiểm tra ý nghĩa “một lần” theo ranh giới lớp/superclass và quy tắc chọn.

Trường hợp muốn số lượng **đối tượng sống trong bộ nhớ tại thời điểm hiện tại** là vấn đề khác: “đã tạo thành công” không đồng nghĩa “còn sống”, và việc theo dõi lifetime/GC không thể suy ra chỉ từ constructor advice.

## 8. Thứ tự advice so với thứ tự khởi tạo Java

Có hai lớp quy tắc cần giữ riêng:

1. **Quy tắc nền của ngôn ngữ:** superclass được xử lý trước phần instance subclass; static initialization có trình tự riêng; constructor chaining chạy theo quy định Java.
2. **Quy tắc của mô hình AOP:** pointcut chọn join point nào, advice được dệt ở đâu, và advice chạy trước/sau/bao quanh với precedence nào.

Một phép đo tại constructor call có thể bắt đầu trước khi một constructor execution join point được thực hiện; nhưng thứ tự tương đối với initialization của lớp, đánh giá đối số, hoặc các advice khác cần xác định trong công cụ tương ứng. Bộ dệt có thể tạo cấu trúc lồng nhau, nên nhật ký thường có dạng:

~~~text
before của một biên gọi
    trước/gần điểm thực thi được chọn
        hành vi khởi tạo gốc
    sau điểm thực thi được chọn
after của một biên gọi
~~~

Đây là **sơ đồ ý tưởng**, không phải stdout chuẩn chung của mọi hệ thống AOP.

### 8.1. Advice after có nhiều ngữ nghĩa

Đừng dùng một từ “after” cho mọi trạng thái mà không phân biệt:

| Kiểu hành vi | Khi nào có ý nghĩa? | Rủi ro nếu hiểu sai |
|---|---|---|
| **Before** | Trước join point mà mô hình định nghĩa | Object có thể chưa hợp lệ |
| **After returning** | Join point kết thúc theo đường bình thường | Dễ nhầm với “giao dịch nghiệp vụ đã commit” |
| **After throwing** | Join point hoàn tất bằng ngoại lệ | Phải hiểu throwable ở ranh giới nào |
| **After/finally** | Khi rời join point theo ngữ nghĩa hỗ trợ, kể cả thành công/lỗi | Có thể ghi “đã tạo” dù constructor thất bại |
| **Around** | Bao lấy và có thể điều phối join point | Có thể bỏ qua, lặp hoặc thay đổi ngữ nghĩa xây dựng object |

Một callback chạy khi rời constructor không chứng minh toàn bộ quá trình tạo object đã hoàn tất nếu vẫn còn constructor trong chuỗi phía ngoài phải chạy. Nếu mục tiêu là “đối tượng hoàn tất xây dựng”, hãy chọn **đúng ranh giới** và thử nghiệm ca constructor chaining.

### 8.2. Thứ tự nhiều aspect không được suy từ tên file

Giả sử cả **ValidationTrace** và **ConstructionMetric** cùng chọn constructor. Nếu mọi advice đều có side effect, thứ tự chúng chạy có thể làm thay đổi log, metric và cả kết quả nếu một advice ném ngoại lệ.

Không có quy tắc chung “file nào được biên dịch trước sẽ chạy advice trước”. Precedence/order là phần thuộc ngữ nghĩa và cấu hình công cụ. Khi cần bảo đảm, khai báo thứ tự hợp lệ theo công cụ và viết kiểm thử xác minh đúng hành vi kỳ vọng.

## 9. Sơ đồ so sánh ba quan sát khác nhau trên một thao tác new

Xét một caller:

~~~java
Child child = new Child();
~~~

Có thể đặt các điểm quan sát khái niệm ở ba phạm vi:

~~~text
CALLER
   │
   ├─ A. constructor-call boundary (nếu cơ chế hỗ trợ)
   │       │
   │       ├─ Class initialization, khi lớp chưa initialized
   │       │
   │       └─ Cấp phát và chuỗi constructor của một object
   │               ├─ B. pre-initialization / initialization
   │               │       của các lớp trong chuỗi
   │               └─ C. constructor-execution
   │                       của các constructor được thực thi
   │
   └─ Caller nhận Child reference nếu thành công
~~~

**Sơ đồ chỉ thể hiện phạm vi quan sát, không áp đặt rằng A luôn xảy ra trước static initializer trong mọi hình thức biểu diễn join point.** Một bộ dệt có thể mô tả các biên và điểm thực thi theo thứ tự riêng, phù hợp với ngữ nghĩa cụ thể.

Dưới góc nhìn thiết kế:

- A giúp gắn hành vi theo **vị trí yêu cầu** một đối tượng.
- B giúp quan sát **vòng đời khởi tạo** ở cấp object/class.
- C giúp gắn hành vi theo **constructor được thực thi**.

Nếu policy nhằm bảo đảm “mọi object thuộc kiểu X đều được khởi tạo hợp lệ”, chặn một số caller chưa chắc đủ. Nếu policy nhằm ghi lại “caller nào yêu cầu tạo object”, quan sát thân constructor có thể thiếu ngữ cảnh caller mong muốn.

## 10. Tình huống đặc biệt: constructor thất bại

Một constructor có thể ném ngoại lệ trước khi hoàn tất. Khi đó:

- Không có reference đã xây dựng thành công được trả về từ biểu thức **new** cho caller.
- Một số initializer hoặc constructor của superclass/subclass có thể đã thực thi một phần và tạo side effect.
- Advice kiểu finally ở điểm đã đi qua vẫn có thể chạy, tùy join point và điểm cắt.
- Advice **after-returning** ở một ranh giới không hoàn tất bình thường không nên bị hiểu như đã ghi nhận tạo thành công.

Giả sử nghiệp vụ ghi sự kiện “khởi tạo thành công” ở advice after-finally. Nếu constructor ném lỗi, event đó trở thành dữ liệu sai. Cần dùng điều kiện thành công và điểm quan sát phù hợp, thường là ranh giới **trả về object đã khởi tạo thành công** theo cơ chế hỗ trợ.

Ngược lại, để thu thập metric “có bao nhiêu lượt thử tạo object, kể cả lỗi”, một điểm ghi ở phía caller trước khi tạo hoặc advice before có thể hợp lý hơn, miễn nó thực sự bao phủ các lượt thử mong muốn.

Không nên dùng một counter duy nhất cho cả “bắt đầu tạo”, “constructor đã chạy” và “đối tượng tạo xong”. Ba chỉ số này đo ba sự kiện khác nhau.

## 11. Tình huống đặc biệt: lớp khởi tạo thất bại

Static field initializer hoặc static block có thể ném lỗi. Trong Java, lỗi khởi tạo có các quy tắc lan truyền và trạng thái lớp riêng; ví dụ một ngoại lệ không phải Error phát sinh trong static initialization có thể được bọc dưới **ExceptionInInitializerError**; các lần dùng lớp đã đánh dấu khởi tạo lỗi có thể gặp **NoClassDefFoundError**.

Từ góc nhìn AOP:

- Advice quanh một static initializer **không được giả định lớp luôn khởi tạo thành công**.
- Việc advisor hoặc advice **chạm đến chính lớp chưa khởi tạo xong** có thể tạo phụ thuộc vòng hoặc quan sát trạng thái chưa ổn định.
- Phải phân biệt lỗi của bộ dệt/agent, lỗi trong static initializer gốc và lỗi do advice được thêm vào.
- Nếu advice ghi metric, hãy dùng nhãn biểu thị **started**, **succeeded** hoặc **failed**, thay vì một nhãn “initialized” không rõ tình trạng.

Khác với lỗi constructor của một instance, lỗi khởi tạo lớp có thể ảnh hưởng **các lần sử dụng cùng định nghĩa lớp về sau**. Đây là lý do advice trong class initialization nên có ít side effect và ít phụ thuộc vòng đời lớp khác nhất có thể.

## 12. Tính an toàn của advice trong giai đoạn khởi tạo

Giai đoạn khởi tạo nhạy cảm vì target có thể ở trạng thái chưa ổn định. Những điều sau cần được xem xét trước khi gắn advice:

### 12.1. Không phát tán đối tượng chưa hoàn tất

Nếu một constructor hoặc advice đưa **this** vào một registry, callback, executor hay listener công khai trước khi khởi tạo xong, mã khác có thể nhìn thấy các trường ở giá trị mặc định hoặc bất biến chưa được thiết lập. Hiện tượng này thường được gọi là **this escape**.

Advice ghi thông tin kỹ thuật nên tránh tham chiếu đến object qua nhiều luồng hoặc gọi mã bên ngoài khi object còn xây dựng dở. Nếu chỉ cần biết kiểu, chữ ký constructor hay thời gian, hãy ưu tiên metadata ít rủi ro thay vì đọc toàn bộ trạng thái.

### 12.2. Không dựa vào method override trong constructor

Khi superclass constructor gọi một phương thức có thể override, Java có thể dispatch đến override của subclass, ngay cả lúc trường instance subclass chưa khởi tạo. Một advice tại constructor execution gọi thêm một phương thức có thể override có thể tạo đường gọi nhạy cảm tương tự.

Không nên dùng lời gọi đó để “xác thực object đã sẵn sàng” nếu target chưa hoàn tất.

### 12.3. Kiểm soát reentrancy

Advice có thể tạo đối tượng mới, ghi log, khởi tạo một helper hoặc nạp một lớp khác. Những hành động đó có thể khớp lại với cùng pointcut và khiến advice chạy lồng nhau.

Ví dụ một aspect theo dõi **mọi constructor** nhưng chính bộ ghi log của aspect cũng tạo object; nếu không loại trừ phần hạ tầng quan sát hoặc không giới hạn phù hợp, điểm can thiệp có thể phát sinh rất nhiều lần ngoài dự kiến.

### 12.4. An toàn đa luồng

Class initialization có cơ chế đồng bộ của JVM; nhưng **advice của bạn vẫn phải tuân theo chính sách đồng bộ đối với trạng thái mà nó chia sẻ**. Khi nhiều object cùng được tạo trên nhiều luồng, advice tại constructor có thể chạy đồng thời. Một biến đếm dùng chung với phép tăng không nguyên tử có thể sai.

Nếu cần metric số lần, dùng cấu trúc an toàn luồng phù hợp và xác định rõ event đếm là trước, sau hay thành công.

### 12.5. Độ ổn định của công cụ

Static initialization và constructor có thể xuất hiện trong nhiều thư viện hạ tầng, kể cả chính thư viện logging/tracing. Pointcut quá rộng dễ tạo tác động dây chuyền, chi phí khởi động lớn hoặc vòng lặp instrumentation.

Hãy chọn tập kiểu rõ ràng, thử trên đường khởi động thật, và kiểm tra sự tương thích giữa cơ chế weaving với class loader cũng như những dạng class mà công cụ hỗ trợ.

## 13. Những giới hạn khi chỉ dùng proxy hoặc factory

Một proxy thông thường làm việc bằng cách nhận **lời gọi phương thức** qua đối tượng đại diện. Với constructor, vấn đề là **đối tượng phải được tạo trước khi có một instance proxy của nó** theo nhiều thiết kế proxy phổ biến.

Một điểm chặn ở factory:

~~~java
interface Factory<T> {
    T create();
}

static <T> T observeCreation(Factory<T> factory) {
    System.out.println("factory: before");
    try {
        return factory.create();
    } finally {
        System.out.println("factory: after");
    }
}
~~~

Đây là **đoạn mã minh họa**, chưa phải chương trình Java độc lập. Caller có thể gọi **observeCreation(() -> new Child())** để bao quanh một đường tạo object. Lời gọi đó ghi begin/end của **factory boundary**; nó không chứng minh static initializer, constructor execution hay object pre-initialization đã được dệt.

Những giới hạn cần nhớ:

1. Nếu code tạo đối tượng **trực tiếp** bằng new mà không đi qua factory, interceptor tại factory không quan sát được đường đó.
2. Factory có thể trả về một object có sẵn hoặc lấy từ pool; một lượt gọi factory chưa chắc tương đương một lần cấp phát/khởi tạo object.
3. Nếu khởi tạo lớp xảy ra trước khi factory được gọi, thời gian đo tại factory không bao gồm class initialization trước đó.
4. Chặn một phương thức **init()** tự đặt tên không đồng nghĩa chặn ngữ nghĩa khởi tạo object của Java.
5. Với bytecode weaving có join point constructor/static initialization thực sự, tập điểm có thể khác, nhưng phải xác minh tính tương thích của bộ dệt và đường thực thi.

Đây là khác biệt cơ bản giữa **chặn một API tạo đối tượng** và **can thiệp vào ngữ nghĩa khởi tạo của ngôn ngữ**.

## 14. Nên đặt concern nào ở giai đoạn nào?

| Nhu cầu | Điểm quan sát đáng cân nhắc | Lý do và điều kiện |
|---|---|---|
| Đo chi phí khởi tạo lớp | Join point class/static initialization nếu hỗ trợ | Đếm theo vòng đời lớp; không suy ra số object |
| Đo thời gian tạo instance theo một API công khai | Biên constructor call hoặc factory nếu bao phủ đúng caller | Gắn với lượt yêu cầu, có thể lấy thời điểm nhận reference |
| Theo dõi constructor nào hoạt động | Constructor execution | Phân biệt overload/chaining; không mặc định mỗi execution là một object |
| Kiểm tra trạng thái sau khi tạo instance thành công | Biên hoàn tất khởi tạo theo mô hình được hỗ trợ | Tránh đọc trạng thái quá sớm |
| Thu metric cho cả lần thử tạo thất bại | Before ở biên yêu cầu + advice lỗi thích hợp | Tách attempted/succeeded/failed |
| Áp dụng quy tắc miền khi object hình thành | Constructor, factory hoặc đối tượng cộng tác rõ ràng | Quy tắc bất biến nên hiện rõ trong thiết kế miền |
| Tự động ghi dấu nhiều vùng của chương trình | Pointcut phù hợp ở các join point được bộ dệt hỗ trợ | Kiểm tra coverage, thứ tự, khả năng tránh reentrancy |

AOP hữu ích nhất khi concern thực sự xuyên cắt nhiều nơi, có phạm vi chọn ổn định và có khả năng xác minh. Đưa toàn bộ logic nghiệp vụ khởi tạo sang aspect có thể khiến object trông như đã hoàn tất trong mã gốc nhưng thực tế phụ thuộc vào advice ẩn, khó kiểm thử hơn.

## 15. Quy trình kiểm tra thứ tự thực thi khi dùng AOP

Bắt đầu từ ví dụ Java thuần đã kiểm chứng. Sau khi có bộ dệt cụ thể, thêm aspect với phạm vi **rất hẹp**, chẳng hạn chỉ một lớp và một loại constructor, rồi làm theo các bước:

1. **Ghi baseline:** lưu stdout/các assertion của chương trình Java trước khi dệt. Xác định rõ lần tạo thứ nhất, thứ hai, trường hợp **this(...)** và superclass.
2. **Đặc tả từng pointcut:** chọn đúng nhóm static initialization, constructor call, constructor execution hay initialization; ghi rõ có được công cụ hỗ trợ không.
3. **Thêm một advice một lần:** chạy lại, xác định điểm xuất hiện của thông điệp advice trong trace.
4. **Thử constructor chaining:** so sánh số sự kiện với số instance và số thân constructor được gọi.
5. **Thử đường lỗi:** cho constructor hoặc initializer thất bại theo kịch bản kiểm thử riêng; xác nhận after-returning/after-throwing/finally đúng nghĩa.
6. **Thử nhiều aspect:** thêm precedence có chủ đích; kiểm tra thứ tự cũng như kết quả.
7. **Thử đường ngoài phạm vi:** tạo đối tượng qua caller khác hoặc qua factory/proxy khác, phát hiện đường đi không được quan sát.
8. **Kiểm tra side effect:** đảm bảo advice không làm object bị phát tán sớm, tăng metric hai lần, ném lỗi mới hoặc thay đổi chức năng ngoài yêu cầu.

Với dệt mã ở compile/load time, chỉ chạy bài kiểm thử trên đúng artifact và JVM/configuration có bộ dệt hoạt động. Gọi thủ công hàm của aspect trong một unit test **không chứng minh** advice đã được áp dụng tại join point thực tế.

### 15.1. Ma trận kiểm thử tối thiểu

| Tình huống | Kỳ vọng cần viết thành assertion |
|---|---|
| Lần sử dụng active đầu của lớp | Static initialization đúng phạm vi, đúng số lần |
| Lần tạo instance thứ hai | Không chạy lại static, có khởi tạo instance |
| Constructor có **this(...)** | Không nhầm các constructor execution với các object mới |
| Constructor của superclass | Phần superclass trước phần instance subclass theo Java |
| Constructor ném ngoại lệ | Không ghi sự kiện “tạo thành công” sai |
| Caller không thuộc pointcut | Không kích hoạt advice ngoài phạm vi |
| Hai aspect cùng áp dụng | Thứ tự ổn định và kết quả đúng |
| Nhiều luồng cùng tạo object | Metric và trạng thái chia sẻ an toàn |
| Class loader khác | Hiểu đúng danh tính lớp và vòng đời khởi tạo độc lập |

## 16. Câu hỏi vận dụng

**Câu 1.** Một điểm đo static initializer ghi nhận 1 lần, nhưng đã có 300 instance được tạo. Có lỗi không?

**Đáp:** Không nhất thiết. Static initialization đo vòng đời lớp, còn constructor/object initialization gắn với các lượt tạo instance. Đếm khác nhau là đúng nếu metric được định nghĩa khác nhau.

**Câu 2.** **new Child()** gọi tiếp **this("default")** và **super()**. Nếu instrument ba constructor execution liên quan, có phải đã tạo ba object?

**Đáp:** Không. Nhiều constructor nằm trong quá trình tạo cùng một instance; phải phân biệt số lần thực thi constructor với số object cấp phát.

**Câu 3.** Chỉ gọi **Class.forName(typeName, false, loader)** có chắc chạy khối static chưa?

**Đáp:** Không; tham số **false** yêu cầu không kích hoạt khởi tạo chỉ vì thao tác này.

**Câu 4.** Một advice before tại constructor đọc toàn bộ trường subclass và gửi **this** sang một luồng khác. Rủi ro gì?

**Đáp:** Các trường có thể còn giá trị mặc định/chưa hợp lệ; object escape khỏi quá trình xây dựng khiến luồng khác quan sát trạng thái chưa hoàn tất.

**Câu 5.** Muốn thống kê số lần caller yêu cầu tạo object qua một factory. Nên chặn static initialization hay biên factory?

**Đáp:** Biên factory; đồng thời cần nhớ một lần gọi factory có thể trả về object sẵn có thay vì cấp phát mới. Tên metric phải phản ánh sự kiện thực đo.

**Câu 6.** Một pointcut constructor-call không ghi log khi object được tạo tại nơi khác. Điều này có chứng minh weaver không hoạt động?

**Đáp:** Chưa. Có thể pointcut chỉ bao phủ một tập caller, hoặc đường thực thi không đi qua cơ chế chặn. Cần kiểm tra phạm vi điểm chọn và cơ chế weave cụ thể.

**Câu 7.** Đọc một **static final int** là hằng compile-time luôn phải khởi tạo lớp khai báo nó?

**Đáp:** Không. Quy tắc constant variable của Java có thể khiến giá trị được dùng mà không khởi tạo lớp.

## 17. Sơ đồ ghi nhớ toàn bộ bài

~~~text
CLASS LIFECYCLE
    load ──► link ──► initialize class (static field/block)
                             │
                             │ thường trước lần new đầu tiên
                             ▼
OBJECT LIFECYCLE
    yêu cầu tạo object ──► cấp phát, giá trị mặc định
                             │
                             ▼
                  chuỗi constructor super / this
                             │
                             ▼
                  instance initializer + constructor body
                             │
                             ▼
                     object tạo thành công
                             │
                             ▼
                     caller nhận reference
~~~

**AOP có thể nhìn các mốc khác nhau của sơ đồ trên** nếu công cụ hỗ trợ: static initialization ở cấp lớp, constructor call từ phía caller, constructor execution ở phía callee, các giai đoạn pre-initialization/initialization ở vòng đời instance. Không có một điểm “khởi tạo” duy nhất đại diện cho mọi sự kiện.

Muốn triển khai đúng, hãy chỉ rõ **sự kiện nào cần quan sát, pointcut chọn loại join point nào, bộ dệt thực sự hỗ trợ đến đâu, advice chạy vào thời điểm nào, object đã có trạng thái gì và tác dụng phụ nào được phép**. Trình tự gốc của Java là cơ sở để đánh giá kết quả sau khi dệt; lời khẳng định về thứ tự advice cần kiểm chứng theo cơ chế AOP đang dùng.

## Tài liệu đối chiếu

- [Java Language Specification, Java SE 17, Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): phân biệt loading, linking, class initialization và object creation.
- [AspectJ Programming Guide — Join Points](https://eclipse.dev/aspectj/doc/released/progguide/semantics-joinPoints.html): một ví dụ mô hình AOP có định nghĩa tường minh constructor call/execution, static initialization, pre-initialization và initialization; không được suy rộng mọi khả năng đó sang mọi công cụ AOP.