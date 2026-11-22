# Kế thừa, ghi đè phương thức và ảnh hưởng của đa hình đối với pointcut AOP

## 1. Vì sao pointcut trở nên khó dự đoán khi có kế thừa?

Trong **Aspect-Oriented Programming (AOP)**, pointcut là quy tắc chọn những **join point** mà advice sẽ can thiệp. Với một lớp độc lập, người học thường bắt đầu từ các ví dụ chọn thực thi phương thức theo tên, kiểu tham số hoặc lớp. Nhưng trong hệ thống hướng đối tượng, người gọi có thể biết một **interface** hoặc **lớp cha**, còn đối tượng thực là một **lớp con**. Lớp con có thể kế thừa nguyên một phương thức, ghi đè nó hoặc bổ sung các overload.

Từ đó xuất hiện những câu hỏi mà tên phương thức không đủ trả lời:

- Caller viết **Base ref = new Child()**, rồi gọi **ref.work()**: biểu thức pointcut nên xét **Base**, **Child** hay cả hai?
- **Child** không override **work()**: thân phương thức nào thực thi và phương thức được khai báo ở lớp nào?
- **Child** override **work()**: join point nào của chương trình đã đổi, và điểm gọi ở caller có thay đổi không?
- Một pointcut chọn **call** có tương đương pointcut chọn **execution** trong mọi tình huống đa hình không?
- Một annotation trên phương thức của lớp cha có tự áp dụng cho phương thức override ở lớp con không?
- Nếu hệ thống dùng **proxy**, mọi lần gọi qua interface và các lời gọi nội bộ có đều đi qua bộ chặn không?

Bài này dùng **quy tắc Java 17+** để xác định điều gì thực sự xảy ra ở runtime, rồi từ đó thiết kế pointcut và kiểm tra advice. Các mô hình AOP khác nhau hỗ trợ những loại join point khác nhau; cú pháp pointcut của một công cụ chỉ là cách biểu diễn cụ thể cho những khái niệm chung ấy.

**Nguyên tắc trung tâm:** phân biệt *kiểu tĩnh và vị trí lời gọi*, *kiểu thực của đối tượng*, *phương thức thực được chọn để chạy* và *cơ chế AOP đang can thiệp vào đâu*. Bốn thông tin có liên quan, nhưng không luôn giống nhau.

## 2. Những khái niệm Java phải hiểu trước khi viết pointcut

### 2.1. Kế thừa

Một lớp con có thể nhận được những phương thức instance có thể kế thừa từ lớp cha. Ví dụ:

~~~java
class Base {
    void inherited() {
        System.out.println("Base.inherited");
    }
}

class Child extends Base {
    // Không khai báo lại inherited()
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Khi một **Child** gọi **inherited()**, thân khai báo tại **Base** thực thi. Việc đối tượng là **Child** không tự sinh thêm một bản thân phương thức tương ứng trong **Child**.

Điều đó quan trọng cho pointcut: nếu chọn theo **lớp chứa khai báo phương thức/thân mã**, điều kiện có thể khớp **Base**; nếu chọn theo **kiểu runtime của receiver**, điều kiện có thể khớp **Child**. Hai kiểu chọn khác nhau.

### 2.2. Ghi đè (overriding)

Một phương thức instance ở lớp con có thể **override** phương thức instance tương ứng được kế thừa từ lớp cha nếu đáp ứng các quy tắc của Java.

~~~java
class Base {
    void process() {
        System.out.println("Base.process");
    }
}

class Child extends Base {
    @Override
    void process() {
        System.out.println("Child.process");
    }
}
~~~

Khi gọi bình thường qua một reference kiểu **Base** nhưng đối tượng thực là **Child**, JVM sử dụng cơ chế **dynamic dispatch** để chọn override thích hợp là **Child.process()**.

### 2.3. Đa hình (polymorphism)

**Kiểu của biến** tại compile time và **kiểu của đối tượng thực** tại runtime có thể khác nhau:

~~~java
Base service = new Child();
service.process();  // Thực thi Child.process()
~~~

Khi giải quyết lời gọi, Java dùng thông tin tĩnh để xác định một phương thức hợp lệ và dạng lời gọi; với lời gọi virtual/interface thích hợp, Java sử dụng lớp thực của đối tượng để chọn triển khai tại runtime.

Bởi vậy, **kiểu tĩnh ảnh hưởng việc biên dịch lời gọi**, còn **kiểu runtime ảnh hưởng phương thức override nào thực thi**.

### 2.4. Overriding khác overloading

**Overriding** thay cách thực hiện cùng một hợp đồng instance ở lớp con. **Overloading** thêm phương thức cùng tên nhưng danh sách tham số khác nhau; việc chọn overload chủ yếu được xác định bằng kiểu tại compile time.

Ví dụ **Base.select(Object)** và **Child.select(String)** là hai overload khác nhau, không phải Child override Base.select(Object). Với biến kiểu **Base**, lời gọi **select("hello")** vẫn có thể chọn **Base.select(Object)** vì compiler chỉ nhìn những overload khả dụng qua **Base**.

### 2.5. Method hiding khác overriding

Phương thức **static** của lớp con có cùng chữ ký với phương thức static của lớp cha là **method hiding** (che khuất), không phải dynamic overriding.

~~~java
class Base {
    static void kind() {
        System.out.println("Base");
    }
}

class Child extends Base {
    static void kind() {
        System.out.println("Child");
    }
}
~~~

**Base.kind()** chạy mã của Base; **Child.kind()** chạy mã của Child. Gọi static qua biến instance tuy Java có thể cho phép ở những ngữ cảnh nhất định nhưng dễ gây nhầm lẫn; nên gọi qua tên lớp. **Pointcut với static call không nên dựa vào suy luận dynamic dispatch.**

## 3. Bốn góc nhìn của một lời gọi phương thức

Xét các thông tin được quan sát tại một lời gọi instance:

| Góc nhìn | Ví dụ | Vai trò khi chọn pointcut |
|---|---|---|
| **Kiểu tĩnh ở call site** | Biến được khai báo là **Base** | Ảnh hưởng cách compiler phân giải biểu thức gọi và chữ ký ở call join point |
| **Đối tượng đích tại runtime** | Instance thực là **Child** | Có thể được lọc bằng điều kiện kiểu runtime như target trong những mô hình hỗ trợ |
| **Khai báo/thân thực thi** | **Child.process()** hoặc **Base.inherited()** | Quyết định execution join point của thân phương thức thực chạy |
| **Vị trí và kiểu mã chứa join point** | Lời gọi nằm trong **Controller**, thân nằm trong **Service** | Quy tắc lexical như within/withincode có thể khớp khác nhau |

Sơ đồ:

~~~text
Caller có reference kiểu Base
             │
             │ gọi ref.process()
             ▼
        CALL join point
        (chữ ký/vị trí gọi)
             │
             ▼
      Java dynamic dispatch
             │
             └──► object thực: Child
                         │
                         ▼
                 Child.process()
                 EXECUTION join point
                         │
                         ▼
                  Advice (nếu khớp)
~~~

Sơ đồ mô tả **một lời gọi instance được dispatch động** và phân biệt những đối tượng quan sát. Không phải mọi công cụ AOP đều phát lộ cả call lẫn execution join point; có công cụ chỉ chặn các lời gọi đi qua đối tượng đại diện.

## 4. Call pointcut và execution pointcut không đồng nghĩa

Một mô hình AOP phong phú, chẳng hạn AspectJ, phân biệt hai loại:

- **Method call join point:** điểm nơi một lời gọi phương thức được phát ra. Thông tin chữ ký ở đó có liên hệ với **kiểu tĩnh dùng để truy cập phương thức**.
- **Method execution join point:** điểm nơi thân một phương thức thực sự bắt đầu và thực thi. Thông tin chữ ký ở đó liên hệ với **kiểu khai báo phương thức đang chạy**.

Ví dụ cú pháp **minh họa theo AspectJ**, với tên kiểu được rút gọn:

~~~text
call(* Base.process(..))
execution(* Base.process(..))
~~~

Hai biểu thức trên **không thể xem là tương đương** trong mọi tình huống đa hình.

Với:

~~~java
Base ref = new Child();
ref.process();
~~~

Caller nhìn hợp đồng **Base.process()** tại biểu thức gọi, nhưng Java dispatch đến override **Child.process()**. Một **call** pointcut liên quan chữ ký Base ở phía caller có thể khớp nơi gọi, trong khi **execution** pointcut chỉ nhắm đích danh thân **Base.process()** sẽ không đồng nghĩa với “mọi lần gọi phương thức process qua reference Base”, bởi override ở Child có thể là thân thực sự chạy.

**Lưu ý về cú pháp và matching:** một bộ chọn chứa mẫu kiểu, ký hiệu subtype và quy tắc match phương thức kế thừa có thể làm tập điểm khớp rộng hơn so với so sánh chính xác tên lớp. Kết luận về một pointcut thực tế phải dựa trên ngữ nghĩa của chính bộ dệt đó và trên việc xác minh điểm khớp; không suy luận chỉ từ cách viết gần giống Java.

### 4.1. Cùng execution có thể được gọi từ nhiều caller

Khi nhiều caller với những kiểu reference khác nhau đều dispatch đến **Child.process()**, chúng có thể tạo ra **nhiều call join point khác nhau** nhưng cùng kích hoạt kiểu **execution join point** của Child.process tại mỗi lượt thực thi.

Nếu mục tiêu là “mỗi lần mã của Child.process chạy”, bắt ở biên thực thi có thể phù hợp. Nếu mục tiêu là “mọi lời gọi phát ra từ lớp ClientX”, chọn ở vị trí call và giới hạn lexical theo ClientX có thể phù hợp hơn.

### 4.2. Cùng call site có thể dispatch đến nhiều execution khác nhau

Một dòng:

~~~java
void invoke(Base service) {
    service.process();
}
~~~

Có thể được gọi với instance Base, Child hoặc một lớp con khác. Vị trí gọi trong **invoke** không đổi, nhưng thân thực thi thay đổi theo runtime receiver. Chính vì thế **chọn call site** khác với **chọn implementation đang chạy**.

### 4.3. Lời gọi super có ngữ nghĩa đặc biệt

Khi mã lớp con viết **super.process()**, Java gọi triển khai phù hợp của superclass theo quy tắc gọi super, thay vì dispatch virtual thông thường từ lớp con xuống chính override của nó.

Trong **mô hình AspectJ cụ thể**, method-call join point không bao gồm các lời gọi **super** đến phương thức instance theo cùng cách call join point thông thường. Tuy nhiên execution join point của phương thức cha vẫn có thể được quan sát nếu nó thực sự chạy. Không được áp đặt đặc điểm đó như giới hạn phổ quát cho tất cả AOP runtime, nhưng nó cho thấy tại sao việc biết loại join point là bắt buộc.

## 5. Kiểu tĩnh và kiểu runtime: chọn bằng mẫu chữ ký hay điều kiện đối tượng?

Một pointcut thường có thể biểu đạt một trong hai ý tưởng:

1. **Chọn theo chữ ký/mẫu kiểu tĩnh:** ví dụ phương thức mang tên process, khai báo trong một họ kiểu xác định.
2. **Chọn theo kiểu runtime của đối tượng:** ví dụ chỉ khi target thực sự là **Child** hoặc một subtype của nó.

Trong một số ngôn ngữ AOP, có thể kết hợp cả hai loại điều kiện.

Giả mã trung lập công cụ:

~~~text
pointcut interesting =
    method-execution named "process"
    AND runtime-target is-a Child

before interesting:
    log("a Child object runs process")
~~~

Ở dạng này, **runtime-target is-a Child** có thể đúng cả khi object Child đang chạy một phương thức được kế thừa nguyên từ Base, nếu loại join point hỗ trợ điều kiện đó và phương thức gốc được instrument.

Đó là khác biệt giữa:

- “**Thân phương thức khai báo ở Child** được thực thi”.
- “**Một đối tượng Child** đang thực hiện thao tác”.

Hai mô tả gần nhau trong hội thoại nhưng dẫn đến pointcut khác nhau.

### 5.1. this và target trong một mô hình AOP có chúng

Ví dụ các pointcut designator **this(Type)** và **target(Type)**:

- Ở **call join point**, **this** thông thường là object đang thực thi mã phía **caller**, còn **target** là object nhận lời gọi.
- Ở **execution join point** của phương thức instance, **this** và **target** thông thường đều gắn với object có phương thức đang thực thi.
- Ở ngữ cảnh static, không có một target instance thích hợp cho các điều kiện này.

Ví dụ giả mã biểu đạt ý tưởng:

~~~text
call to Base.process
AND target instance-of Child
AND this instance-of CommandHandler
~~~

Điều kiện trên hướng đến “**CommandHandler gọi phương thức mà receiver runtime là Child**”, chứ không đơn thuần “Child đang chạy một phương thức”.

**Chú ý:** ý nghĩa chính xác của this/target, tính khả dụng của object ở join point và cú pháp kết hợp phải đọc theo ngôn ngữ AOP cụ thể. Đặc biệt không được tự đồng nhất **this** với proxy, target hay caller trong mọi cơ chế interception.

### 5.2. Điều kiện subtype với ký hiệu + trong AspectJ

Trong type pattern của AspectJ, hậu tố **+** thể hiện kiểu được chỉ định cùng các subtype của nó. Một ví dụ mẫu chữ ký:

~~~text
execution(* example.Base+.process(..))
~~~

Nó truyền đạt ý định chọn execution của **process** trong phạm vi kiểu **Base và các subtype** theo quy tắc matching của AspectJ.

Đừng lẫn **Base+** với phép kiểm tra kiểu runtime của mọi object. Pattern trong **execution** xét chữ ký và phạm vi join point theo ngôn ngữ; khi một phương thức **kế thừa nhưng không override**, kiểu khai báo execution vẫn có thể là Base. Nếu yêu cầu thật sự phụ thuộc receiver runtime, hãy biểu đạt hoặc kiểm thử riêng điều kiện ấy, không suy từ dấu + rằng công cụ đã đọc mọi kiểu instance tại runtime.

Tương tự, **Base+** không tự giải quyết việc lớp cần quan sát có được đưa vào phạm vi weaving hoặc lời gọi có đi qua interceptor hay không.

## 6. Kế thừa phương thức nhưng không override

Xét:

~~~java
class Base {
    void inherited() {
        System.out.println("Base.inherited");
    }
}

class Child extends Base {
    // Không override inherited()
}
~~~

Nếu gọi **new Child().inherited()**, JVM có thể thực thi **thân Base.inherited()**. Không có thân **Child.inherited()** mới được tạo chỉ vì object thuộc Child.

Khi một pointcut giới hạn bằng lớp chứa mã thực thi, ví dụ “bên trong mã khai báo trực tiếp ở Child”, phương thức inherited có thể nằm ngoài tập chọn dù object runtime là Child.

Có ít nhất ba chính sách khác nhau:

| Yêu cầu | Cách nghĩ về điểm chọn |
|---|---|
| Quan sát mọi lần thực thi thân **Base.inherited()** | Chọn execution của phương thức được khai báo tại Base |
| Quan sát thao tác inherited khi receiver là **Child** | Chọn execution thích hợp và điều kiện runtime target thuộc Child nếu cơ chế hỗ trợ |
| Quan sát các caller trong một module gọi **inherited** | Chọn call join point theo vị trí caller, có thể thêm điều kiện target |

**Lưu ý quan trọng về static weaving:** nếu thân **Base.inherited()** không nằm trong tập lớp được dệt, pointcut kiểm tra runtime target cũng không tự làm advice xuất hiện từ hư không. Phải xác minh bytecode hoặc đường gọi mà bộ dệt thực sự kiểm soát.

### 6.1. Override làm thay đổi execution pointcut

Khi Child khai báo:

~~~java
@Override
void inherited() {
    System.out.println("Child.inherited");
}
~~~

Thân mới thuộc Child. Một pointcut trước đó chỉ gắn vào thân Base có thể không còn quan sát các lượt gọi dispatch đến override. Đây là một dạng **thay đổi mức bao phủ sau refactor** dù các caller không hề sửa lời gọi.

Khi chính sách cần áp dụng nhất quán cho cả họ class, nên khai báo rõ phạm vi subtype hoặc hợp đồng interface, và kiểm thử cả subclass có override lẫn subclass chỉ kế thừa.

## 7. Ví dụ Java 17 đầy đủ: đa hình, override, overload và proxy

Ví dụ sau tách biệt các hiện tượng có thể gây sai pointcut:

- **Base ref = new Child()** gọi override theo runtime.
- **Base.outer()** gọi **inner()**; khi object là Child, lời gọi nội bộ vẫn dispatch đến **Child.inner()**.
- **inherited()** và **final fixed()** chạy thân kế thừa từ Base.
- **select(Object)** và **select(String)** là overload; lựa chọn phụ thuộc kiểu reference/khả năng gọi ở compile time.
- **kind()** là static method hiding.
- Một **JDK dynamic proxy** chặn lời gọi qua interface **Action**. Trong **outer()**, lời gọi nội bộ **inner()** không đi lại qua proxy trong ví dụ này, dù JVM dispatch đúng đến Child.inner.

Tạo file **PolymorphismPointcutDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class PolymorphismPointcutDemo {
    interface Action {
        void outer();
        void inner();
    }

    static class Base implements Action {
        @Override
        public void outer() {
            System.out.println("Base.outer");
            inner();
        }

        @Override
        public void inner() {
            System.out.println("Base.inner");
        }

        public void inherited() {
            System.out.println("Base.inherited");
        }

        public final void fixed() {
            System.out.println("Base.fixed");
        }

        public static void kind() {
            System.out.println("Base.kind");
        }

        public void select(Object value) {
            System.out.println("Base.select(Object)");
        }
    }

    static class Child extends Base {
        @Override
        public void inner() {
            System.out.println("Child.inner");
        }

        public static void kind() {
            System.out.println("Child.kind");
        }

        public void select(String value) {
            System.out.println("Child.select(String)");
        }
    }

    static Action proxy(Action target) {
        return (Action) Proxy.newProxyInstance(
                Action.class.getClassLoader(),
                new Class<?>[]{Action.class},
                (proxy, method, args) -> {
                    System.out.println("intercept: " + method.getName());
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        Base value = new Child();
        System.out.println("direct:");
        value.outer();
        value.inherited();
        value.fixed();
        value.select("text");
        ((Child) value).select("text");
        value.kind();
        Child.kind();

        System.out.println("proxy:");
        Action observed = proxy(value);
        observed.outer();
        observed.inner();
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 PolymorphismPointcutDemo.java
java PolymorphismPointcutDemo
~~~

Stdout chính xác:

~~~text
direct:
Base.outer
Child.inner
Base.inherited
Base.fixed
Base.select(Object)
Child.select(String)
Base.kind
Child.kind
proxy:
intercept: outer
Base.outer
Child.inner
intercept: inner
Child.inner
~~~

**Phân tích các dòng:**

1. **value.outer()** gọi thân **Base.outer()**, vì Child không override outer. Bên trong outer, **inner()** là instance method được Child override, nên Java dispatch đến **Child.inner()**.
2. **value.inherited()** và **value.fixed()** sử dụng thân của Base. **fixed** là final, không thể được Child override; điều đó không ngăn một cơ chế bytecode weaving hỗ trợ execution của final method quan sát thân đó.
3. **value.select("text")** chọn **Base.select(Object)** vì kiểu khai báo của value là Base và compiler không nhìn overload **Child.select(String)** qua Base.
4. Ép kiểu **(Child) value** làm overload **select(String)** trở nên khả dụng, nên gọi bản của Child.
5. **value.kind()** là lối gọi static qua biến nên vẫn chọn **Base.kind()** theo kiểu tĩnh; **Child.kind()** gọi bản Child. Trong mã thực tế nên viết **Base.kind()** để tránh hiểu nhầm.
6. **observed.outer()** đi qua proxy nên có **intercept: outer**. Sau khi handler ủy quyền cho Base.outer của object Child, lời gọi **inner()** bên trong đối tượng chạy trực tiếp và dispatch đến Child.inner nhưng không tạo thêm dòng **intercept: inner**.
7. **observed.inner()** là một lời gọi độc lập qua proxy, nên có dòng **intercept: inner** trước **Child.inner**.

**Ranh giới của ví dụ:** đây là Java thuần với JDK dynamic proxy, **không phải bộ dệt bytecode** và không phải khẳng định rằng mọi công cụ AOP chỉ có thể quan sát hai phương thức thuộc Action. Ví dụ chủ yếu kiểm chứng dispatch Java và sự phụ thuộc của interception vào đường đi thực tế.

## 8. Kế thừa interface và implementation

Interface có thể định nghĩa hợp đồng mà nhiều class implement:

~~~java
interface Payment {
    void pay();
}

class CardPayment implements Payment {
    @Override
    public void pay() {
        // Thực hiện thanh toán thẻ
    }
}

class BankPayment implements Payment {
    @Override
    public void pay() {
        // Thực hiện thanh toán ngân hàng
    }
}
~~~

Đây là đoạn minh họa, các thân method hiện chưa thực hiện nghiệp vụ thanh toán. Khi caller khai báo **Payment payment**, runtime có thể dispatch đến **CardPayment.pay** hoặc **BankPayment.pay**.

Có thể có ba cách đặt chính sách:

- **Theo hợp đồng:** mọi triển khai của Payment phải được ghi nhận.
- **Theo nhóm implementation:** chỉ CardPayment hoặc chỉ những class thuộc package cụ thể.
- **Theo ngữ cảnh runtime:** chỉ những object/argument thỏa điều kiện tại lần gọi cụ thể.

Nếu dùng **execution pointcut** chỉ khớp một implementation, việc bổ sung class implement khác có thể không tự được bao phủ. Nếu dùng một **call pointcut** tại các vị trí gọi qua interface, bạn có thể quan sát lời gọi xuất phát từ những caller đã được weave, nhưng các caller khác hoặc đường nội bộ vẫn phải được đánh giá riêng.

**Điểm cần kiểm chứng:** có công cụ nhận diện pointcut ở phương thức interface dựa trên metadata rồi suy ra implementation; có công cụ dựa theo bytecode/thân phương thức; có cơ chế proxy chỉ thấy method khai báo trên interface. Không nên mặc định rằng định nghĩa pointcut bằng tên interface sẽ tự động bao phủ mọi implementation trên mọi engine.

## 9. Khi lớp con ghi đè: annotation được kế thừa đến đâu?

Một trường hợp hay gây sai lệch là đặt annotation đánh dấu policy lên phương thức ở Base, sau đó một subclass override nhưng không sao chép annotation.

Trong Java, **method annotation không tự động được kế thừa như class annotation có @Inherited**. **@Inherited** có cơ chế dành cho annotation trên class (theo quy tắc Java); nó không tự khiến phương thức override nhận annotation của phương thức cha.

Ví dụ Java 17 chạy được:

Tạo file **OverrideAnnotationDemo.java**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

public class OverrideAnnotationDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed {}

    static class Base {
        @Observed
        public void process() {}
    }

    static class Child extends Base {
        @Override
        public void process() {}
    }

    static class Inheriting extends Base {}

    public static void main(String[] args) throws NoSuchMethodException {
        var baseMethod = Base.class.getDeclaredMethod("process");
        var childMethod = Child.class.getDeclaredMethod("process");
        var inheritedMethod = Inheriting.class.getMethod("process");

        System.out.println("base declared annotated=" +
                baseMethod.isAnnotationPresent(Observed.class));
        System.out.println("child declared annotated=" +
                childMethod.isAnnotationPresent(Observed.class));
        System.out.println("inherited method owner=" +
                inheritedMethod.getDeclaringClass().getSimpleName());
        System.out.println("inherited method annotated=" +
                inheritedMethod.isAnnotationPresent(Observed.class));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 OverrideAnnotationDemo.java
java OverrideAnnotationDemo
~~~

Stdout chính xác:

~~~text
base declared annotated=true
child declared annotated=false
inherited method owner=Base
inherited method annotated=true
~~~

**Ý nghĩa đối với pointcut:**

- Nếu pointcut dựa trên **annotation trực tiếp ở phương thức đang được thực thi**, override **Child.process()** có thể không khớp khi Child không có annotation.
- Nếu một framework/công cụ chủ động đi ngược lên interface/superclass để tìm metadata chính sách, kết quả có thể khác. Đây là **quy tắc riêng của công cụ**, không phải do Java tự động gắn method annotation vào override.
- **Inheriting** không override; lời gọi **getMethod("process")** tìm được phương thức khai báo tại **Base**, và annotation vẫn nằm trên chính phương thức đó.

Khi chính sách dựa vào annotation, cần xác định nó có ý nghĩa **trên declaration**, **trên hợp đồng interface**, **trên implementation** hay **trên toàn bộ override chain**. Không nên dùng từ “kế thừa annotation” mà không xác định cơ chế đọc metadata.

## 10. Chọn theo nơi khai báo, nơi thực thi hay nơi caller đặt lệnh?

Trong mô hình pointcut giàu khả năng như AspectJ, một số bộ chọn lexical thường được diễn giải như sau:

- **within(TypePattern):** chọn join point có mã nằm **bên trong kiểu** phù hợp.
- **withincode(MethodPattern):** chọn join point nằm trong **thân phương thức/constructor chứa đoạn mã**, theo ngữ nghĩa cụ thể.
- **execution(MethodPattern):** chọn join point nơi thân method khớp được thực thi.
- **call(MethodPattern):** chọn join point tại vị trí thực hiện lời gọi khớp pattern.

Ví dụ ý tưởng:

~~~text
call(* *.process(..)) && within(example.client..*)
~~~

Biểu thức loại này chọn lời gọi đến process trong vùng caller thuộc **example.client** (với quy tắc wildcards của ngôn ngữ đó). Nó **không** tự nghĩa là thân **process()** phải được khai báo bên trong example.client.

Ngược lại:

~~~text
execution(* example.impl..*.process(..))
~~~

nhằm chọn execution phương thức ở vùng implementation được mô tả bởi chữ ký. Khi Child chỉ kế thừa thân Base, một điều kiện lexical yêu cầu thân mã nằm ở Child không tự đúng.

### 10.1. Cẩn thận khi kết hợp call và within

Một method call vào **Child.process()** có thể phát ra từ một method nằm trong **BaseCaller**, **ChildCaller** hoặc bất kỳ nơi nào khác. Tập caller hoàn toàn độc lập với việc phương thức đích được override.

Khi cần chặn “mọi caller của một API thuộc phạm vi X”, quyết định áp dụng theo call site thường mang ý nghĩa rõ. Khi cần chặn “mọi lần thực thi của một thân nghiệp vụ bất kể caller”, execution thường diễn tả mục đích tốt hơn nếu cơ chế hỗ trợ.

### 10.2. Một phương thức có thể vừa khớp mẫu kiểu vừa không khớp within

Ví dụ receiver runtime là Child, nhưng mã đang chạy là **Base.inherited()**. Điều kiện **target(Child)** có thể đúng ở execution của inherited theo mô hình hỗ trợ runtime target; điều kiện **within(Child)** không đương nhiên đúng, bởi thân method nằm ở Base.

Kết hợp quá nhiều điều kiện AND khi chưa hiểu từng điều kiện có thể làm pointcut vô tình thành rỗng. Thử từng điều kiện độc lập và ghép dần sẽ dễ xác minh.

## 11. Trường hợp final, private, static và super

Kế thừa và đa hình ở Java có những giới hạn khiến thuật ngữ “ghi đè” không áp dụng được cho mọi method:

| Loại phương thức/lời gọi | Ngữ nghĩa Java | Hệ quả cho pointcut |
|---|---|---|
| **Instance method có thể override** | Dynamic dispatch đến triển khai phù hợp theo runtime type | Execution có thể nằm ở subclass; call site có thể chỉ biết superclass/interface |
| **Final instance method** | Không thể bị subclass override | Vẫn có thân method để thực thi; weaving tại bytecode có thể quan sát nếu công cụ hỗ trợ, nhưng proxy tạo subclass không thể override final method |
| **Private method** | Không được override như virtual method kế thừa | Không dựa vào dynamic overriding; proxy interface không tự chặn private method |
| **Static method** | Method hiding, không có dynamic overriding | Chọn theo chữ ký static, không giả định target runtime instance |
| **Lời gọi super.method()** | Sử dụng quy tắc super invocation đặc biệt | Call join point có thể khác hoặc không được hỗ trợ giống lời gọi virtual; execution của thân cha vẫn có thể được quan sát |
| **Constructor** | Không được kế thừa/override như instance method | Cần join point constructor riêng khi muốn chặn khởi tạo |

**Final không đồng nghĩa tuyệt đối “mọi AOP đều không thể áp dụng”.** Giới hạn áp dụng khác nhau giữa tạo subclass proxy và bytecode weaving có khả năng can thiệp tại execution. Tương tự, private method không xuất hiện trong giao diện proxy, nhưng một bytecode weaver phù hợp có thể hỗ trợ execution join point ở đó.

Các nhận định như “AOP bỏ qua tất cả final method” hoặc “pointcut luôn bắt được private method” đều quá rộng. Cần nói cụ thể **cơ chế** và **loại join point**.

## 12. Java generics, bridge method và chữ ký có thể gây ngạc nhiên

Generics trong Java được biên dịch chủ yếu bằng **type erasure**. Khi override những phương thức có kiểu generic/covariant return, compiler có thể sinh ra **synthetic bridge method** để duy trì khả năng dispatch và tương thích chữ ký bytecode.

Ví dụ ý tưởng:

~~~java
interface Reader<T> {
    T read();
}

final class StringReader implements Reader<String> {
    @Override
    public String read() {
        return "value";
    }
}
~~~

Đây là một đoạn minh họa không có main. Trên bytecode, compiler có thể thêm bridge để đáp ứng hợp đồng đã xóa kiểu. Một công cụ quan sát bytecode ở mức thấp có thể nhìn thấy thêm method synthetic, còn một công cụ AOP cấp cao có thể diễn giải bridge và method gốc theo quy tắc riêng.

Từ đó có ba điều cần kiểm tra:

1. Pointcut chọn theo signature của **source Java**, signature đã qua erasure hay metadata của join point do công cụ cung cấp?
2. Advice có được áp dụng một lần cho một lời gọi nghiệp vụ hay có thể xuất hiện ở nhiều tầng method/bridge khi công cụ cho phép?
3. Sau khi đổi kiểu generic hoặc kiểu trả về covariant, tập join point được chọn có thay đổi không?

Không nên mặc định mỗi method hiển thị trong IDE tương ứng đúng một method vật lý ở bytecode và đúng một event advice cho mọi engine.

## 13. Proxy runtime với đa hình: ranh giới của đường đi

Một proxy làm trung gian nhận cuộc gọi, có thể chạy advice rồi ủy quyền cho target. Đó là **một hình thức interception**; không phải toàn bộ AOP và không có cùng năng lực với mọi kiểu weaving.

Trong ví dụ Java 17 phần 7, proxy được tạo cho **Action**:

~~~text
Caller
  │
  ▼
Action proxy
  │
  ├─ interceptor nhận outer()
  │
  ▼
Child object (target)
  │
  ▼
Base.outer()            ← thân kế thừa
  │
  └─ gọi inner() nội bộ
         │
         ▼
      Child.inner()     ← dynamic dispatch
      (không đi lại qua Action proxy)
~~~

Điều này minh họa hai quy tắc độc lập:

- **Java polymorphism vẫn hoạt động** bên trong target: Child.inner được chọn.
- **Proxy interception chỉ kích hoạt với lời gọi qua proxy**: inner nội bộ không quay lại handler trong ví dụ.

Nếu có một bytecode weaver chèn advice trực tiếp tại **Child.inner() execution**, lời gọi inner nội bộ vẫn có thể được quan sát, vì đường đi không nhất thiết phụ thuộc proxy. Nhưng phải xác nhận method thực sự được weave và pointcut khớp.

### 13.1. Interface method và implementation method nhìn khác nhau

Trong JDK dynamic proxy, đối tượng Method được gửi cho handler có thể biểu diễn method thuộc interface mà proxy triển khai; instance target vẫn có thể là một subclass cụ thể. Vì vậy thông tin reflection tại proxy handler không tự nói rằng bytecode execution đang nằm trong lớp chứa method interface.

Một policy chọn method dựa trên annotation ở interface và một policy chọn annotation ở implementation có thể cho kết quả khác nếu công cụ không tự hợp nhất metadata. Kiểm tra đối tượng Method, khai báo interface, override và quy tắc lookup của interceptor thực tế.

### 13.2. Một đường gọi không qua proxy không tạo event interceptor

Nếu code giữ cả tham chiếu **proxy** và tham chiếu **target**, người gọi trực tiếp target sẽ bỏ qua handler. Điều đó không làm thay đổi dynamic dispatch: override của subclass vẫn chạy bình thường.

Khi cần cam kết bao phủ, phải xác định **caller được phép giữ tham chiếu nào**, có đường truy cập trực tiếp nào tồn tại hay không và pointcut được thực thi bằng proxy hay weaving. Chỉ định nghĩa interface hoặc một aspect không tự bảo đảm tất cả đường đi đều chảy qua interceptor.

## 14. Những tác động khi thêm một subclass vào hệ thống

Giả sử ban đầu chỉ có **BaseService.process()** và pointcut quan sát thân Base. Sau này có **VipService extends BaseService** ghi đè process, thêm kiểm tra riêng.

Có thể xảy ra:

1. **Caller vẫn biên dịch như cũ:** nó gọi qua BaseService.
2. **Runtime dispatch đổi:** đối tượng VipService khiến thân **VipService.process()** chạy.
3. **Execution join point cần xét lại:** rule chỉ chọn chính xác thân Base có thể không quan sát hành vi mới.
4. **Call join point ở một số caller giữ nguyên:** nếu rule chọn nơi gọi theo kiểu Base, những caller đã được weave vẫn có thể khớp; nhưng caller mới/kiểu gọi mới cần kiểm tra.
5. **Annotation có thể khác:** override VipService không mặc nhiên nhận method annotation từ Base.
6. **Precedence giữa các advice có thể đổi:** policy chung và policy riêng cùng khớp có thể chạy chồng.

Vậy việc thêm subclass là **một thay đổi có thể ảnh hưởng phạm vi AOP**, kể cả khi API công khai không đổi. Đây là lý do nên gắn **kiểm thử mức bao phủ** với các lớp con quan trọng thay vì chỉ test code Base.

## 15. Cách thiết kế pointcut bền vững trước kế thừa và override

Trước khi chọn biểu thức pointcut, hãy mô tả concern bằng một câu chính xác:

- “Mọi lượt **thực thi** của hành vi thanh toán, bất kể implementation”.
- “Mọi lời gọi API thanh toán **từ một nhóm caller**”.
- “Chỉ theo dõi phương thức khai báo trực tiếp trong **PremiumPayment**”.
- “Chỉ theo dõi khi **receiver runtime** thuộc một subtype cụ thể”.
- “Chỉ theo dõi khi **method declaration** mang annotation được chỉ định”.

Những phát biểu này **không tương đương**, dù có thể đều được mô tả ngắn bằng câu “theo dõi Payment”.

### 15.1. Lựa chọn trục phân loại

Có thể tổ chức điều kiện trên các trục:

| Trục | Ví dụ | Câu hỏi kiểm tra |
|---|---|---|
| **Loại join point** | call, execution | Chặn ở nơi gọi hay nơi thực thi? |
| **Hợp đồng kiểu** | interface, base type, subtree | Class mới thêm vào có được bao phủ theo ý định không? |
| **Tên/chữ ký** | process, pay, tham số | Overload hoặc bridge có gây trùng/thiếu không? |
| **Kiểu runtime** | target là VipService | Với object kế thừa method, điều kiện vẫn đúng chứ? |
| **Vị trí lexical** | caller thuộc package A | Một lớp mới ở package khác có bị bỏ sót không? |
| **Annotation/metadata** | @Observed | Override có annotation trực tiếp không; engine tìm annotation ở đâu? |
| **Đường chặn thực tế** | proxy, weaving | Có đường gọi bỏ qua hoặc lớp không nằm trong phạm vi dệt không? |

### 15.2. Ưu tiên hợp đồng ổn định khi concern là chung

Nếu một policy áp dụng cho mọi implementation của một giao diện, hãy làm cho **ý định toàn họ kiểu** trở nên rõ qua thiết kế API, type pattern/hợp đồng hoặc metadata của công cụ. Nếu policy chỉ áp dụng cho subclass đặc biệt, biểu thức nên chỉ rõ subclass và lý do lựa chọn đó.

Mẫu tên package quá rộng có thể bắt thêm mã ngoài ý định. Mẫu quá cụ thể vào một implementation có thể bỏ sót subtype mới. Không có một pointcut “đúng nhất” cho mọi trường hợp; độ rõ của **chính sách nghiệp vụ/kỹ thuật** mới quyết định loại pointcut.

### 15.3. Điều kiện phủ định có thể khó hơn điều kiện khẳng định

Ví dụ ý tưởng:

~~~text
all payment executions
AND NOT methods declared in Base
~~~

Nếu subclass kế thừa method Base, điều kiện “declared in Base” vẫn có thể áp dụng dù receiver runtime là subclass. Nếu mục đích thật là “mọi instance của subclass, kể cả method kế thừa”, điều kiện phủ định theo declaring type có thể sai.

Khi loại trừ lớp hoặc method, nên test các trường hợp: Base trực tiếp, subclass override, subclass kế thừa, interface implementation và lời gọi qua proxy.

## 16. Phạm vi dệt là điều kiện độc lập với pointcut

Một pointcut diễn đạt đúng vẫn có thể không kích hoạt nếu mã liên quan **không nằm trong phạm vi được công cụ AOP áp dụng**.

Với weaving ở compile time hoặc load time, cần kiểm tra:

- Các class thuộc Base và Child có được đưa vào phạm vi dệt không?
- Một implementation được load bởi class loader khác có được instrument không?
- Aspect có chọn **execution** ở nơi mã phương thức thực chạy, hay chỉ có call site đã dệt?
- Có phương thức mới được compiler sinh ra (bridge/synthetic) mà policy chưa xem xét không?

Với runtime proxy, cần kiểm tra:

- Proxy được tạo ở interface/lớp nào?
- Caller nhận proxy hay target gốc?
- Lời gọi **self-invocation** hoặc lời gọi đến method không lộ trên proxy có được chặn không?
- Công cụ có giới hạn với final/private/static method không?

**Không có tư cách “được bảo đảm áp dụng” chỉ bằng cách một subclass extends đúng lớp cha.** Bảo đảm chỉ có ý nghĩa khi biết điểm join có được hỗ trợ, pattern có khớp, cơ chế dệt có kiểm soát đúng mã/đường gọi và test chứng minh hành vi.

## 17. Phân biệt advice chạy nhiều lần với nhiều lần thực thi nghiệp vụ

Một lời gọi instance có thể tạo ra nhiều join point lồng nhau:

~~~text
Caller gọi Child.process()
    ├─ method-call join point
    ├─ method-execution Child.process()
    │     └─ Child.process() gọi super.process()
    │             └─ execution Base.process()
    └─ caller nhận kết quả
~~~

Trong một bộ dệt hỗ trợ cả call/execution, nếu pointcut chọn rộng nhiều nhóm điểm, **một lượt nghiệp vụ** có thể kích hoạt advice ở nhiều giai đoạn.

Nếu mục tiêu metric là “một giao dịch thanh toán”, đếm cả call vào Child, execution Child, execution Base và lời gọi ở helper sẽ tạo số đếm lớn hơn một. Việc advice xuất hiện nhiều lần không nhất thiết là bug của weaver; có thể rule đã chọn nhiều join point khác nhau như thiết kế.

### 17.1. Kiểm soát overlap giữa các aspect

Giả sử có policy chung cho Base và policy riêng cho Child. Khi Child được tạo và override process:

- Rule chung có thể khớp theo phạm vi subtype, metadata interface hoặc runtime target.
- Rule riêng có thể khớp chính xác Child.
- Hai advice có thể chạy cùng một join point và tạo log trùng hoặc tương tác thứ tự.

Cần xác định policy nào chịu trách nhiệm: policy chung, policy riêng bổ sung hay policy riêng thay thế. Khai báo precedence nếu công cụ hỗ trợ, và dùng kiểm thử đếm invocation để phát hiện trùng bất ngờ.

### 17.2. Around advice có thể đổi dispatch bằng cách đổi đích gọi

Một **around advice** có thể điều phối việc chạy hành vi gốc, thậm chí thay target hoặc trả kết quả khác nếu cơ chế cho phép. Không nên giả định mọi around advice luôn gọi đúng implementation mà Java sẽ dispatch nếu không có aspect.

Khi advice thay đổi đường thực thi, hãy xem lại bảo toàn kết quả, ngoại lệ, tính bất biến và việc gọi lại override/super. Một retry không có idempotency hoặc một lệnh gọi thêm super có thể khiến side effect lặp lại.

## 18. Kiểm thử tập điểm khớp và thứ tự thực thi

Điểm quan trọng nhất là **kiểm thử đúng tính chất của pointcut**, không chỉ kiểm thử nội dung một advice khi gọi bằng tay.

Nên dựng fixture có ít nhất:

~~~text
Interface Contract
       ▲
       │
Base implements Contract
       ▲
       ├── InheritingChild      (không override)
       ├── OverridingChild      (override)
       └── SpecializedChild     (override + overload)
~~~

Với cùng caller, thử lần lượt các runtime target. Sau đó thay caller để kiểm tra call site: qua interface, qua base reference, qua child reference và qua proxy nếu ứng dụng dùng proxy.

### 18.1. Ma trận kiểm thử đề xuất

| Tình huống | Câu hỏi cần xác nhận |
|---|---|
| Base gọi trực tiếp | Advice có khớp thân/method Base như dự định không? |
| Child kế thừa không override | Pointcut có xét declaring type của Base hay runtime type của Child? |
| Child override | Execution advice có bám theo thân mới không? |
| Caller qua interface | Chữ ký call và implementation được chọn ra sao? |
| Caller qua Base reference | Runtime dispatch đến Child có được AOP quan sát đúng? |
| Caller qua Child reference | Tập overload ở compile time có thay đổi không? |
| Method static/final/private | Cơ chế AOP có hỗ trợ loại điểm muốn chặn không? |
| Child gọi super.method | Có phát sinh advice ở execution của superclass không? |
| Method annotation chỉ ở Base | Override có được engine coi là annotated không? |
| Child tự gọi method khác | Có self-invocation bỏ qua proxy không? |
| Hai pointcut cùng khớp | Advice có chạy trùng hoặc sai precedence không? |
| Compiler tạo bridge | Số lượt advice có giữ đúng kỳ vọng không? |

### 18.2. Xác minh số lượt và thứ tự

Khi thử, ghi log có ít nhất:

- Loại join point: **call** hay **execution**.
- Chữ ký method được mô hình AOP báo cáo.
- Kiểu khai báo, kiểu runtime của target nếu có.
- Nơi gọi hoặc enclosing method nếu công cụ cung cấp.
- Một id cho lượt gọi để phân biệt các invocations lồng nhau.
- Thứ tự **before**, **around/proceed**, **after returning/throwing**.

Không nên chỉ in tên phương thức: với override và overload, nhiều phương thức có thể cùng tên nhưng khác signature hoặc declaring type.

### 18.3. Kiểm thử cả trường hợp không khớp

Nếu pointcut chỉ được phép quan sát Child, hãy chứng minh Base thuần không bị advice chạy. Nếu chỉ được phép quan sát call từ package giao tiếp bên ngoài, hãy chứng minh call nội bộ không tự lọt vào tập.

Các test “không được chạy” thường phát hiện pointcut quá rộng; các test “phải chạy” phát hiện pointcut thiếu subtype hoặc bỏ qua override.

## 19. Những sai lầm thường gặp

**Sai lầm 1 — “Biến kiểu Base thì lúc nào cũng chạy Base.method.”** Với virtual/interface method có override, Java dispatch theo runtime receiver, nên thân Child có thể chạy.

**Sai lầm 2 — “Object Child thì mọi method execution được khai báo ở Child.”** Method kế thừa không override có thể thực thi thân khai báo ở Base.

**Sai lầm 3 — “Overload là override.”** Compiler giải quyết overload theo kiểu và phương thức khả dụng tại compile time; override là cơ chế chọn thân tại runtime.

**Sai lầm 4 — “call và execution bắt đúng một tập join point.”** Call nằm ở chỗ gọi, execution ở chỗ thực thi; đa hình khiến hai phía có thể gắn với các kiểu khai báo khác nhau.

**Sai lầm 5 — “Pointcut kiểm tra target Child tương đương pointcut within Child.”** Một điều kiện dựa vào runtime receiver, điều kiện khác dựa vào vị trí lexical trong mã. Method kế thừa thể hiện khác biệt đó.

**Sai lầm 6 — “Method annotation luôn truyền sang override.”** Java không tự kế thừa annotation của method khi override; công cụ có thể tìm siêu lớp theo quy tắc riêng, phải xác minh.

**Sai lầm 7 — “Final/private method không thể can thiệp bằng bất kỳ AOP nào.”** Khả năng tùy cơ chế. Proxy thông thường có giới hạn khác với bộ dệt bytecode có các join point tương ứng.

**Sai lầm 8 — “Pointcut Base+ nghĩa là mọi object Base/Child đều chắc chắn được quan sát.”** Pattern còn phụ thuộc join point, phạm vi weaving và đường gọi.

**Sai lầm 9 — “Đã đi qua proxy một lần thì mọi lời gọi bên trong target cũng qua proxy.”** Trong ví dụ JDK dynamic proxy, lời gọi nội bộ vẫn dispatch Java đúng nhưng không kích hoạt handler thêm lần nữa.

**Sai lầm 10 — “Log trùng nghĩa là runtime gọi nghiệp vụ hai lần.”** Một lượt gọi có thể phát sinh nhiều join point và nhiều advice; cần phân biệt sự kiện quan sát với số lần thân nghiệp vụ thực chạy.

**Sai lầm 11 — “Refactor kế thừa không ảnh hưởng AOP vì tên method không đổi.”** Thêm override có thể đổi declaring/execution method, annotation lookup, kiểu target và số advice khớp.

## 20. Cách ra quyết định với một pointcut có đa hình

Hãy trả lời tuần tự:

1. **Policy theo lời gọi hay theo thân thực thi?** Đó là quyết định giữa call/execution hoặc đường interception có sẵn.
2. **Policy thuộc hợp đồng interface, lớp cha hay chỉ một implementation?** Đó là cách chọn họ kiểu và phạm vi metadata.
3. **Policy phụ thuộc kiểu tĩnh hay runtime type?** Không trộn hai ý tưởng trong một điều kiện mơ hồ.
4. **Method có thể được kế thừa không override, override, overload hoặc sinh bridge không?** Mỗi trường hợp ảnh hưởng tập chữ ký và điểm thực thi.
5. **Có phải một lần nghiệp vụ cần đúng một event?** Kiểm tra chồng call/execution, super invocation, nested method và các aspect khác.
6. **Cơ chế AOP có thật sự can thiệp vào join point đó không?** Đánh giá bytecode weaving/proxy, class loader, phạm vi instrument và đường gọi.
7. **Đã kiểm thử cả trường hợp khớp và không khớp chưa?** Dùng fixture chứa Base, Child override, Child kế thừa và interface caller.

## 21. Tự kiểm tra

**Câu 1.** **Base ref = new Child()** và Child override **process()**. Tại sao một execution pointcut chọn chính xác thân Base.process có thể không quan sát lượt gọi này?

**Đáp:** Java dispatch đến thân Child.process; điều kiện chọn chính xác thân Base khác với việc chọn mọi lời gọi qua reference kiểu Base.

**Câu 2.** **Child extends Base** nhưng không override **inherited()**. Điều kiện dựa vào runtime target Child và điều kiện dựa vào declaring type Child có giống nhau không?

**Đáp:** Không. Đối tượng có runtime type Child nhưng thân được khai báo ở Base.

**Câu 3.** Với **Base value = new Child()**, Base có **select(Object)**, Child thêm **select(String)**. Vì sao **value.select("x")** không nhất thiết gọi overload String?

**Đáp:** Compiler giải quyết overload thông qua kiểu tĩnh Base; overload chỉ khai báo ở Child không có trong tập ứng viên qua Base.

**Câu 4.** Một Child override phương thức có **@Observed** tại Base nhưng không chép annotation. Dùng reflection của Java kiểm tra annotation trên chính phương thức Child có chắc thấy @Observed không?

**Đáp:** Không; method annotation không mặc nhiên kế thừa qua overriding. Engine có thể có logic lookup riêng nhưng phải xác minh.

**Câu 5.** Proxy intercept **outer()**, mà target.outer gọi trực tiếp **inner()**. Java vẫn chọn Child.inner, nhưng handler có bắt thêm inner không?

**Đáp:** Không trong mô hình dynamic proxy ở ví dụ; inner được gọi bên trong target và không đi qua proxy. Một công cụ weave trực tiếp execution của inner có thể có hành vi khác.

**Câu 6.** Bài test chỉ xác nhận output nghiệp vụ đúng sau khi thêm subclass. Đã đủ để chứng minh pointcut bao phủ subclass chưa?

**Đáp:** Chưa. Phải đo advice có chạy ở join point dự định, chạy đúng số lần, trên đúng implementation, kể cả ca không khớp và gọi lồng nhau.

**Câu 7.** Hai advice cùng log khi một caller gọi Child.process. Có thể khẳng định nghiệp vụ đã chạy hai lần không?

**Đáp:** Không. Có thể hai advice cùng chọn một join point, hoặc một advice chọn call và một advice chọn execution. Cần log loại join point và đếm riêng thân nghiệp vụ.

## 22. Mô hình ghi nhớ

~~~text
              LỜI GỌI TRONG MÃ NGUỒN
              reference type / call site
                         │
                         ▼
                Phân giải ở compile time
                (chữ ký, overload, khả năng gọi)
                         │
                         ▼
                CALL JOIN POINT (nếu hỗ trợ)
                         │
                         ▼
               RUNTIME RECEIVER OBJECT
               Base? Child? Subclass khác?
                         │
                         ▼
                 Dynamic method lookup
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       Body ở Base              Override ở Child
       (kế thừa)                (ghi đè)
             │                       │
             └───────────┬───────────┘
                         ▼
              EXECUTION JOIN POINT
              của thân thực sự chạy
                         │
                         ▼
                  Advice nếu khớp
                         │
                         ▼
                      Trả về
~~~

**Hai kết luận cần giữ đồng thời:** Java quyết định phương thức thực thi theo các quy tắc static resolution và dynamic dispatch; AOP quyết định có gắn advice hay không theo **loại join point, chữ ký, runtime context và cơ chế dệt/chặn lời gọi**. Kế thừa, override và đa hình không phải trường hợp ngoại lệ hiếm, mà là điều kiện thường trực khi viết pointcut cho ứng dụng hướng đối tượng.

## Tài liệu đối chiếu

- [Java Language Specification, Java SE 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): giải quyết lời gọi phương thức, chọn overload và dynamic method lookup.
- [Java Language Specification, Java SE 17, §8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): quan hệ khai báo phương thức, overriding và method hiding.
- [AspectJ Programming Guide — Language Semantics / Join Points](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): ví dụ mô hình AOP phân biệt call/execution, chữ ký static/declaring type và this/target. Cú pháp của AspectJ chỉ được dùng làm ví dụ về một ngôn ngữ AOP cụ thể.
