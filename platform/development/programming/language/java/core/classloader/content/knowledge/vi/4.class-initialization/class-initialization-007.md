# Đọc static field kế thừa: kiểu thực sự khai báo field

## 1. Vấn đề: `Child.value` làm lớp nào khởi tạo?

Xét hai lớp:

~~~java
class Parent {
    static int value = 42;
}

class Child extends Parent {
}
~~~

Java cho phép đọc biến qua hai cách **Parent.value** và **Child.value**. Trong cả hai trường hợp, **field thực sự thuộc Parent**: Child chỉ kế thừa khả năng truy cập nó, không nhận một bản sao biến static.

Theo **JLS §12.4.1**, khi một static field được sử dụng mà **không phải constant variable**, chỉ class/interface **thực sự khai báo field** mới bị khởi tạo do phép truy cập ấy. Vì vậy, **Child.value** có thể làm **Parent initialized**, nhưng không tự làm **Child initialized**. Đó là điểm trọng tâm của bài học.

Bài này giúp bạn xác định declaring class khi có inheritance, phân biệt field hiding và trường hằng được compiler in-line, đọc dấu vết initialization, kiểm tra bằng reflection và tránh nhầm lẫn giữa việc gọi tên Child với thực sự sử dụng thành viên của Child.

## 2. Ba tên có thể khác nhau

Để phân tích **Child.value**, cần tách ba câu hỏi:

| Khái niệm | Câu hỏi | Giá trị trong ví dụ |
| --- | --- | --- |
| **Qualifier** | Tên kiểu nào viết trước dấu chấm? | Child |
| **Declaring class** | Class/interface nào *khai báo* field được lookup chọn? | Parent |
| **Initialization target** | Kiểu nào cần initialization bởi việc đọc static field runtime này? | Parent |

Không nên kết luận kiểu cần khởi tạo chỉ bằng cách nhìn chữ bên trái dấu chấm.

Nếu **Child** không khai báo value, member lookup tìm thấy field kế thừa từ **Parent**. Không có cơ chế override field giống instance method. Nếu sau đó Child tự khai báo field cùng tên thì nó **hide** field của Parent: lúc này **Child.value** và **Parent.value** là hai field khác nhau.

### 2.1 Static field là trạng thái của khai báo kiểu

Static field không được sao chép thành một vùng nhớ mới cho mỗi subclass. Nếu Parent khai báo **static int count**, thì:

~~~java
long before = Child.count;
Child.count = 30;
long after = Parent.count;
~~~

Cả phép đọc và gán ở đây đều hướng tới **Parent.count** (giả sử Child không tự khai báo count và kiểu của count phù hợp). Giá trị **after** sẽ là 30. Không tồn tại một **Child.count** độc lập trong trường hợp này.

### 2.2 Trạng thái initialized không đồng nghĩa loaded

Ngay cả khi **Child** chưa thực thi static initializer, JVM vẫn có thể đã **load** hoặc **link** Child. Cơ chế loading tìm/tạo biểu diễn lớp; linking xác minh, chuẩn bị, phân giải tham chiếu; initialization mới thực thi logic static. Bài này đo và giải thích **điều kiện initialization**, không dùng số dòng log để khẳng định chính xác thời điểm loading hoặc linking.

## 3. Quy tắc khởi tạo từ Java Language Specification

Với một kiểu **T**, initialization xảy ra ngay trước các hành động active use đáng chú ý:

1. T là class và instance của T được tạo.
2. Một static method **do T khai báo** được gọi.
3. Một static field **do T khai báo** được gán.
4. Một static field **do T khai báo** được dùng, và field không phải **constant variable**.

Khi class T initialized, JVM khởi tạo những superclass chưa khởi tạo của T trước. Các superinterface khai báo default methods cũng có quy tắc liên quan. Interface initialization không mặc nhiên khởi tạo toàn bộ superinterface.

Đối với **Child.value** mà value chỉ được Parent khai báo, trường hợp số 4 liên quan đến **Parent**, không phải Child.

~~~text
Parent
  ├─ static int value = 42;
  └─ static { ... }    ← code chạy khi Parent initialized
       ▲
       │ extends
       │
Child
  └─ static { ... }    ← không chạy chỉ vì đọc Parent.value

        đọc Child.value
               │
               ▼
    lookup → Parent.value
               │
               ▼
    initialize Parent nếu cần
               │
               ▼
        đọc Parent.value
~~~

Quy tắc ngược chiều cần nhớ: **new Child()** hoặc active use của **field Child tự khai báo** sẽ khiến Child khởi tạo; khi đó Parent phải initialized trước Child. Điều này không có nghĩa đọc một trường kế thừa tự khởi tạo toàn bộ nhánh kế thừa.

## 4. Ví dụ chạy được số 1: đọc trường kế thừa

Tạo tệp **InheritedStaticFieldDemo.java**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int count = initializeCount();

        static int initializeCount() {
            System.out.println("Parent: initialize count");
            return 42;
        }

        static {
            System.out.println("Parent: static block");
        }
    }

    static class Child extends Parent {
        static int own = 7;

        static {
            System.out.println("Child: static block");
        }
    }

    public static void main(String[] args) {
        System.out.println("1. Before inherited field");
        System.out.println("2. Child.count = " + Child.count);
        System.out.println("3. After inherited field");
        System.out.println("4. Parent.count = " + Parent.count);
        System.out.println("5. Child.own = " + Child.own);
        System.out.println("6. Child.count again = " + Child.count);
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

Stdout chính xác:

~~~text
1. Before inherited field
Parent: initialize count
Parent: static block
2. Child.count = 42
3. After inherited field
4. Parent.count = 42
Child: static block
5. Child.own = 7
6. Child.count again = 42
~~~

### Giải thích các mốc

- Khi in dòng 1, chưa có phép đọc static field từ Parent hoặc Child.
- Để tính **Child.count** ở dòng 2, chương trình cần field **Parent.count**. JVM initialized Parent: trước tiên thực thi **initializeCount()**, sau đó khối static theo thứ tự xuất hiện trong khai báo Parent. Kết quả được in ra là 42.
- Sau dòng 3, **Child: static block** chưa xuất hiện. Đọc static field kế thừa không gây initialization của Child.
- Dòng 4 đọc lại cùng biến Parent.count nên không khởi tạo Parent lần nữa.
- Dòng 5 đọc **Child.own**; vì **own được Child khai báo** và không phải constant variable, JVM initialized Child. Parent đã initialized nên chỉ có dòng của Child được in.
- Dòng 6 đọc field thuộc Parent vốn đã được khởi tạo, nên không còn thông báo static nào.

**Điểm cần hiểu:** output chứng minh khi nào các **static initializers** được thực thi. Nó không khẳng định trước dòng 5 Child chưa hề được nạp hoặc chưa hề được liên kết.

## 5. Cách Java chọn field: member lookup và declaring class

Giả sử:

~~~java
class Base {
    public static long total = 100;
}

class Derived extends Base {
}
~~~

Cả **Base.total** lẫn **Derived.total** đều truy cập field do Base khai báo:

~~~java
long first = Base.total;
long second = Derived.total;
~~~

Nếu **Derived** chưa khai báo trường cùng tên, không có quyết định runtime dựa vào đối tượng thuộc Derived hay Base. Trường được **ràng buộc tĩnh** theo quy tắc tra thành viên ở Java.

Cách viết tên subclass có thể khiến người đọc nghĩ rằng một static initializer của Derived phải chạy. Trên thực tế, trường được chọn vẫn là **Base.total**.

Không nên khẳng định rằng compiler luôn phải phát sinh đúng cùng một tham chiếu constant pool cho cả hai biểu thức. Bytecode có thể chứa symbolic references và được JVM field resolution xử lý theo quy tắc đặc tả. Điều quan trọng là **field thực sự được phân giải tới khai báo nào**.

### 5.1 Đọc và ghi một trường kế thừa

Với Base.total ở trên:

~~~java
Derived.total = 250;
System.out.println(Base.total); // 250
~~~

Đây vẫn là phép gán và đọc **Base.total**. Nếu Base chưa initialized, phép gán static field của Base phải kích hoạt initialization Base trước khi cập nhật. Không có initialization Derived bắt buộc chỉ vì cú pháp dùng tên Derived.

### 5.2 Viết bằng tên declaring class sẽ rõ ràng hơn

Khi đã biết field là của Base, nên viết **Base.total**. Điều này bộc lộ nơi sở hữu biến, giúp code review dễ nhận ra thời điểm khởi tạo và tránh bị hiểu nhầm khi người khác thêm field trùng tên vào subclass.

## 6. Dùng biến tham chiếu để truy cập static field

Java cho phép dùng một primary expression bên trái dấu chấm khi truy cập field static:

~~~java
Derived reference = null;
long value = reference.total;
~~~

Đây là cú pháp hợp lệ dù IDE có thể cảnh báo. Vì total là static, giá trị của **reference** không được dereference để lấy field. Nếu reference là null, việc đọc **không ném NullPointerException** chỉ vì tham chiếu null.

Theo **JLS §15.11.1**, primary expression vẫn phải được **đánh giá**, nhưng kết quả của nó bị bỏ qua khi field là static. Điều này đặc biệt quan trọng nếu phần qualifier có side effect.

Ví dụ minh họa:

~~~java
static Derived obtainReference() {
    System.out.println("qualifier evaluated");
    return null;
}

// Đặt trong một method:
long result = obtainReference().total;
~~~

Nếu biểu thức này được thực thi, dòng **qualifier evaluated** vẫn xuất hiện. Sau khi tính xong qualifier, phép đọc vẫn truy cập field **Base.total** và chỉ yêu cầu initialization của Base nếu cần.

**Phân biệt:** nếu field không static, truy cập qua tham chiếu null có thể ném NullPointerException; và với **new Derived().total**, chính thao tác **new Derived()** đã khiến Derived initialized từ trước khi đọc static field, nên đó là ví dụ **không phù hợp** để kiểm tra riêng trigger của field access.

**Khuyến nghị:** static field nên được truy cập qua tên kiểu khai báo như **Base.total**, không qua reference hoặc tên subclass nếu muốn tránh hiểu sai.

## 7. Ngoại lệ quan trọng: compile-time constant không kích hoạt initialization

Quy tắc active use đối với **đọc static field** loại trừ **constant variable**.

Theo JLS §4.12.4, constant variable là biến **final**, có kiểu **primitive** hoặc **String**, được khởi tạo bằng **constant expression**. Với field như vậy, javac thường đưa giá trị hằng trực tiếp vào bytecode caller (inlining), thay vì phát sinh đọc field runtime.

| Khai báo static | Có phải constant variable? | Phép đọc tự kích hoạt initialization? |
| --- | --- | --- |
| **static final int LIMIT = 100;** | Có | Không. |
| **static final String NAME = "Java";** | Có | Không. |
| **static final long MASK = 1L << 3;** | Có | Không. |
| **static int count = 100;** | Không | Có, nếu class chưa initialized. |
| **static final int SIZE = Integer.parseInt("100");** | Không | Có. |
| **static final Integer BOXED = 100;** | Không | Có. |
| **static final Object TOKEN = new Object();** | Không | Có. |

Từ khóa **final** không tự tạo constant variable. Một field có giá trị chỉ được tính khi runtime, hoặc field có kiểu Object/Integer, không thuộc ngoại lệ này.

### 7.1 Ví dụ chạy được số 2: hằng kế thừa so với field tính lúc chạy

Tạo **InheritedConstantDemo.java**:

~~~java
public class InheritedConstantDemo {
    static class Parent {
        static {
            System.out.println("Parent initialized");
        }

        static final int LIMIT = 64;
        static final String NAME = "core";
        static final int COMPUTED = compute();

        static int compute() {
            System.out.println("Parent.compute()");
            return 9;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("limit = " + Child.LIMIT);
        System.out.println("name = " + Child.NAME);
        System.out.println("computed = " + Child.COMPUTED);
    }
}
~~~

~~~bash
javac InheritedConstantDemo.java
java InheritedConstantDemo
~~~

Stdout:

~~~text
limit = 64
name = core
Parent initialized
Parent.compute()
computed = 9
~~~

Giải thích:

1. Parent.LIMIT và Parent.NAME là **constant variables**. Việc đọc chúng thông qua tên **Child** không tự khởi tạo Parent hoặc Child.
2. **COMPUTED** không phải compile-time constant vì initializer gọi method. Lần đọc **Child.COMPUTED** làm JVM initialized **Parent**.
3. Trong Parent, static block xuất hiện trước khai báo COMPUTED; nên in **Parent initialized** rồi **Parent.compute()**.
4. Child không khai báo bất kỳ field nào đang được đọc, nên **Child initialized** không xuất hiện.

### 7.2 Hệ quả của inlining khi nâng cấp thư viện

Giả sử một thư viện định nghĩa **public static final int LIMIT = 64**. Client đã biên dịch có thể mang giá trị 64 trong bytecode. Nếu thư viện đổi LIMIT thành 128 mà không biên dịch lại client, client vẫn có thể thấy 64. Điều này khác với static field không phải constant variable, được đọc từ định nghĩa runtime.

Khi thiết kế API, dùng constant variable cho hằng bất biến về mặt hợp đồng; không coi đó là cơ chế cấu hình có thể thay riêng lúc triển khai.

## 8. Field hiding: khi Child khai báo cùng tên

Nếu Child có khai báo riêng:

~~~java
class Parent {
    static int score = 10;
}

class Child extends Parent {
    static int score = 20;
}
~~~

Lúc này **Parent.score** và **Child.score** là hai field độc lập. Field lookup chọn theo kiểu xuất hiện trong mã nguồn, không phải virtual override.

- **Parent.score** → đọc field Parent.
- **Child.score** → đọc field Child.
- **Parent ref = new Child(); ref.score** → đọc Parent.score dựa trên **kiểu tĩnh Parent**.
- **Child ref = new Child(); ref.score** → đọc Child.score dựa trên **kiểu tĩnh Child**.

Khi đọc field do Child khai báo, JVM initialized Child nếu chưa. Việc initialization Child cũng đòi hỏi superclass Parent initialized trước nếu cần.

### 8.1 Ví dụ chạy được số 3: field hiding có hai vùng nhớ

Tạo **StaticFieldHidingDemo.java**:

~~~java
public class StaticFieldHidingDemo {
    static int initial(String owner, int value) {
        System.out.println(owner + " field initialized");
        return value;
    }

    static class Parent {
        static int score = initial("Parent", 10);
    }

    static class Child extends Parent {
        static int score = initial("Child", 20);
    }

    public static void main(String[] args) {
        Parent parentRef = null;
        Child childRef = null;

        System.out.println("parentRef.score = " + parentRef.score);
        System.out.println("childRef.score = " + childRef.score);
        System.out.println("Parent.score = " + Parent.score);
        System.out.println("Child.score = " + Child.score);
    }
}
~~~

~~~bash
javac StaticFieldHidingDemo.java
java StaticFieldHidingDemo
~~~

Stdout:

~~~text
Parent field initialized
parentRef.score = 10
Child field initialized
childRef.score = 20
Parent.score = 10
Child.score = 20
~~~

Khi **parentRef.score** được đọc lần đầu, Parent initialized. Khi **childRef.score** được đọc, Child initialized vì score được Child khai báo. Parent đã initialized trước đó. Hai tham chiếu đều null, nhưng các phép truy cập static hợp lệ không dereference null.

Đây là ví dụ minh họa field hiding. Code thực tế nên viết **Parent.score** và **Child.score** cho rõ.

### 8.2 Không nhầm field hiding với method overriding

| Cú pháp | Cơ chế chính |
| --- | --- |
| **ref.field** | Field được lựa chọn theo **kiểu tĩnh** của ref và member lookup. |
| **ref.instanceMethod()** | Method có thể được override; **runtime dispatch** thường chọn implementation theo object thực. |
| **Child.field** kế thừa từ Parent | Vẫn là field thuộc Parent. |
| **Child.field** do Child tự khai báo | Field khác với Parent.field; Child là owner. |

Không áp dụng nguyên tắc **polymorphism của instance methods** cho static fields.

## 9. Reflection: kiểm tra field thực sự được khai báo ở đâu

Trong Java Reflection có ba API phù hợp:

- **Class.getField(name)** tìm **public fields**, kể cả field public được kế thừa.
- **Class.getDeclaredField(name)** chỉ tìm field **do Class đang xét tự khai báo** (bất kể public/private), không tìm field thừa hưởng.
- **Field.getDeclaringClass()** trả về Class/interface **thực sự chứa khai báo field**.

Đó là cách kiểm tra owner thay vì đoán dựa trên cú pháp **Child.field**.

### 9.1 Ví dụ chạy được số 4: reflection và initialization

Tạo **InheritedFieldReflectionDemo.java**:

~~~java
import java.lang.reflect.Field;

public class InheritedFieldReflectionDemo {
    static class Parent {
        public static int LEVEL = initialize();

        static int initialize() {
            System.out.println("Parent initialized");
            return 5;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        Field field = Child.class.getField("LEVEL");

        System.out.println("declaring class = "
                + field.getDeclaringClass().getSimpleName());
        System.out.println("declared by Child = "
                + (field.getDeclaringClass() == Child.class));

        try {
            Child.class.getDeclaredField("LEVEL");
            System.out.println("Child declares LEVEL");
        } catch (NoSuchFieldException expected) {
            System.out.println("Child does not declare LEVEL");
        }

        System.out.println("reflected value = " + field.get(null));
    }
}
~~~

~~~bash
javac InheritedFieldReflectionDemo.java
java InheritedFieldReflectionDemo
~~~

Stdout:

~~~text
declaring class = Parent
declared by Child = false
Child does not declare LEVEL
Parent initialized
reflected value = 5
~~~

**Child.class** và tra metadata không làm Child initialized. **getField("LEVEL")** trả field public kế thừa từ Parent; **getDeclaredField("LEVEL")** trên Child không tìm thấy vì Child không tự khai báo LEVEL. Khi **field.get(null)** đọc giá trị của static field, Parent được initialized trước khi trả 5. Không có dòng **Child initialized**.

**Chú ý:** các thao tác reflection khác như đọc static field, gọi static method hoặc khởi tạo instance có thể kích hoạt initialization. Đừng khái quát rằng “reflection luôn không khởi tạo class”; phải xét đúng API và thao tác.

## 10. Static field của interface cũng tuân theo owner

Field khai báo trong interface mặc nhiên là **public static final**. Tuy vậy, nó không nhất thiết là constant variable: initializer có thể là lời gọi method.

Ví dụ:

~~~java
interface ParentFlags {
    int DYNAMIC = compute();

    static int compute() {
        System.out.println("ParentFlags initialized");
        return 8;
    }
}

interface ChildFlags extends ParentFlags {
    String LABEL = announce();

    static String announce() {
        System.out.println("ChildFlags initialized");
        return "child";
    }
}
~~~

Khi chương trình đọc **ChildFlags.DYNAMIC**, field được **ParentFlags** khai báo và không phải constant variable. JVM khởi tạo **ParentFlags**, không tự khởi tạo ChildFlags chỉ vì tên qualifier là ChildFlags.

Nếu sau đó đọc **ChildFlags.LABEL**, đây là field được ChildFlags khai báo và không phải constant variable, nên ChildFlags initialized. Khởi tạo một interface **không mặc nhiên** làm toàn bộ superinterface khởi tạo, khác với class/superclass.

Cũng cần cẩn thận khi class implements nhiều interface cùng khai báo field cùng tên: **member lookup có thể mơ hồ**, gây lỗi biên dịch. Hãy truy cập qua tên declaring interface để làm rõ ý nghĩa.

## 11. Quy trình chẩn đoán truy cập Sub.FIELD

Khi cần dự đoán static block nào chạy, hãy lần lượt hỏi:

1. **FIELD thuộc member nào được Java chọn?** Kiểm tra Child tự khai báo hay kế thừa. Nếu có field hiding, xác định chính xác field qua kiểu tĩnh và member lookup.
2. **FIELD có thực sự là static không?** Instance fields có quy tắc truy cập khác.
3. **Declaring type của field là ai?** Có thể là superclass hoặc interface, dù code viết **Sub.FIELD**.
4. **FIELD có phải constant variable không?** final + primitive/String + constant expression thì phép đọc không tự trigger initialization.
5. **Declaring type đã initialized chưa?** Nếu chưa và field cần truy cập runtime, JVM sẽ initialize kiểu đó.
6. **Có hành động khác kích hoạt Sub trước đó không?** Ví dụ new Sub(), gọi static method do Sub khai báo hoặc đọc field riêng của Sub.
7. **Nếu Sub được khởi tạo thì superclass đã được khởi tạo chưa?** JVM đảm bảo superclass có liên quan được khởi tạo trước Sub.
8. **Có nhiều class loader định nghĩa lớp cùng tên không?** Trạng thái initialized gắn với từng định nghĩa runtime Class, không chỉ string tên lớp.

Một sơ đồ:

~~~text
    Gặp Sub.FIELD
         │
         ▼
  Lookup FIELD
         │
         ├── do Sub khai báo ──────→ owner = Sub
         │
         └── kế thừa từ Parent ───→ owner = Parent
                                    │
                                    ▼
                        static? constant variable?
                            │               │
                         Không             Có
                            │               │
                   quy tắc khác      đọc constant không
                                      tự yêu cầu initialize
                            │
                            ▼
                  static, non-constant
                            │
                            ▼
                    initialize owner
                     nếu chưa init
                            │
                            ▼
                   đọc hoặc gán field
~~~

Ở đây “owner” là class/interface khai báo field, không phải object đang dùng làm qualifier.

## 12. So sánh các thao tác dễ nhầm

Giả sử **Parent** khai báo **static int X**, **static final int LIMIT = 7**; **Child extends Parent** và khai báo **static int OWN**:

| Thao tác đầu tiên | Kiểu cần initialized do thao tác | Vì sao |
| --- | --- | --- |
| **int a = Child.X;** | Parent | X được Parent khai báo và không phải constant. |
| **Child.X = 9;** | Parent | Gán static field do Parent khai báo. |
| **int a = Parent.X;** | Parent | Cùng field Parent.X. |
| **int n = Child.LIMIT;** | Không do đọc hằng | LIMIT là constant variable. |
| **int a = Child.OWN;** | Parent rồi Child nếu cả hai chưa init | OWN thuộc Child; khi init Child phải init superclass. |
| **new Child()** | Parent rồi Child nếu chưa init | Active use do tạo instance Child. |
| **Class<?> c = Child.class;** | Không tự khởi tạo Child | Class literal không là trigger initialization. |
| **Class.forName(binaryNameChild)** | Child và các điều kiện superclass | Dạng một đối số yêu cầu initialization. |
| **Class.forName(binaryNameChild, false, loader)** | Không chủ động init Child | Overload có boolean false. |

Nếu Child là nested class, binary name thường chứa **$**; không thể dùng tên đơn giản **"Child"** bất kể package/nesting trong Class.forName. Mục tiêu của bảng là so sánh **nguyên nhân khởi tạo**, không phải thay thế quy tắc đặt tên nhị phân.

## 13. Quan sát bytecode bằng javap

Sau khi biên dịch các ví dụ:

~~~bash
javap -c -p InheritedStaticFieldDemo
javap -c -p InheritedConstantDemo
~~~

Phép đọc một static field runtime thường dùng bytecode **getstatic**, phép gán thường dùng **putstatic**. Compiler có thể in-line **constant variables** bằng các lệnh tải hằng, nên không có getstatic tương ứng ở caller.

Tuy nhiên, không nên suy từ một tên được thấy trong bytecode rằng lớp đó **chắc chắn khởi tạo**: JVM có field resolution xác định khai báo thực tế. Cũng không nên mặc định mọi compiler phát sinh constant pool references giống nhau dù có cùng ngữ nghĩa Java.

Khi muốn xem loading trên HotSpot/JVM hỗ trợ Unified Logging, có thể thử:

~~~bash
java -Xlog:class+load=info InheritedStaticFieldDemo
java -Xlog:help
~~~

**class+load** có thể hiện lớp đã nạp và nguồn của lớp. Dấu hiệu **static initializer chạy** vẫn cần quan sát riêng từ chương trình. Logging format và mức độ chi tiết phụ thuộc JVM/JDK; tránh coi một dòng class loading là bằng chứng về initialization.

## 14. Những lỗi và hiểu nhầm thường gặp

### “Đọc Child.counter không thấy Child static block.”

Hãy tìm nơi khai báo **counter**. Nếu Parent khai báo, Java đang truy cập **Parent.counter**, và quy tắc initialization chỉ yêu cầu Parent. Nếu Child tự khai báo trường cùng tên, đó là field hiding và kết luận khác.

### “static final chắc chắn đã initialized khi đọc.”

Sai đối với **constant variables**; đọc **static final int X = 5** không tự làm class initialized. Ngược lại, **static final int X = Integer.parseInt("5")** được tính runtime, vẫn có thể kích hoạt initialization. Kiểu Integer/Object cũng không phải compile-time constant variable.

### “Tôi thấy Parent và Child đều initialized sau khi đọc field kế thừa.”

Có thể đã có **active use khác** của Child trước đó, chẳng hạn **new Child()** hoặc **Child.OWN**. Để kiểm tra, tạo chương trình đơn giản mới và chỉ đọc **Child.inheritedField** trước mọi hành động khác. Khi static initialization đã thành công một lần, đọc tiếp không chạy lại các khối static.

### “reference.field là static, reference null thì phải NullPointerException.”

Không đúng. Khi field là static, giá trị qualifier bị bỏ qua sau khi đánh giá biểu thức. Nếu qualifier có side effect hoặc lỗi trong quá trình đánh giá, side effect/lỗi vẫn xảy ra. Với instance field, quy tắc dereference null khác.

### “Lần chạy này class đã load nên chắc chắn static block đã chạy.”

Không. Loading và initialization là những pha khác nhau. Một class có thể đã load/link mà chưa initialized. Đừng gộp ba khái niệm vào một từ “load class”.

### “Một JAR thay đổi constant mà client vẫn thấy giá trị cũ.”

Nếu constant variable đã được compiler in-line, cần biên dịch lại client. Đây là hệ quả tương thích nhị phân và cách mã hóa constant, không phải lỗi khởi tạo subclass.

### “NoSuchFieldError xảy ra khi dùng Sub.FIELD.”

Đó có thể là vấn đề khác phiên bản binary, class loader hoặc field resolution (ví dụ thư viện runtime không còn field caller đã biên dịch tham chiếu). Kiểm tra classpath/module path và phiên bản artifact; không tự quy lỗi cho quy tắc initialization.

## 15. Tự kiểm tra kiến thức

**1.** Parent khai báo **static int cache = 1**, Child extends Parent và có static block. Lần đầu in **Child.cache** làm lớp nào initialized?

**Đáp án:** Parent. cache thực sự thuộc Parent. Child không bị khởi tạo chỉ do phép đọc này.

**2.** Nếu Child tự khai báo **static int cache = 2**, lần đầu đọc Child.cache thì sao?

**Đáp án:** Đây là field mới thuộc Child. Nếu chưa lớp nào initialized, superclass Parent được khởi tạo trước rồi đến Child.

**3.** Parent khai báo **static final String VERSION = "v1"**. Vì sao Child.VERSION không tự init Parent?

**Đáp án:** VERSION là constant variable (final, kiểu String, constant expression). Phép đọc constant không phải active use kích hoạt initialization.

**4.** **Parent p = new Child(); System.out.println(p.score);** chọn score theo kiểu tĩnh hay kiểu runtime?

**Đáp án:** Theo kiểu tĩnh Parent và quy tắc field lookup. Nhưng **new Child()** đã khởi tạo Child và superclass từ trước; cần tách riêng tác động này khi phân tích output.

**5.** Vì sao **Child.class.getField("LEVEL").getDeclaringClass()** trả Parent.class?

**Đáp án:** getField có thể tìm field public được kế thừa, còn getDeclaringClass trả về nơi định nghĩa field thực sự.

**6.** Parent khai báo **static final Object TOKEN = new Object()**. Đọc **Child.TOKEN** có kích hoạt Parent không nếu chưa init?

**Đáp án:** Có. Object không phải primitive hoặc String constant variable; final không đủ để loại trừ initialization.

**7.** Interface A khai báo **int N = compute()**, interface B extends A. Đọc B.N lần đầu thì interface nào khởi tạo?

**Đáp án:** A, do N được A khai báo và không phải constant variable. Không tự init B chỉ vì B xuất hiện trong cú pháp.

**8.** Nếu cả Parent.field và Child.field có cùng tên do mỗi lớp tự khai báo, đổi biến tham chiếu từ kiểu Parent sang Child sẽ thay đổi trường nào được đọc?

**Đáp án:** Có thể thay đổi: field lookup theo kiểu tĩnh, nên hai khai báo khác nhau có thể được chọn. Không phải override động.

## 16. Ghi nhớ

**Quy tắc cốt lõi:** Khi truy cập static field kế thừa, hãy xác định **class/interface thực sự khai báo field**, không dựa vào tên subclass đứng trước dấu chấm.

- Field kế thừa vẫn thuộc declaring type; không có bản sao static tự động ở subclass.
- Đọc hoặc gán static field runtime yêu cầu initializing **declaring type** nếu cần.
- Nếu subclass tự khai báo field cùng tên, đó là **field hiding** và là một trường riêng.
- Compile-time constant variable là ngoại lệ: phép đọc hằng không tự kích hoạt initialization.
- Java field access ràng buộc tĩnh theo kiểu, khác instance method overriding.
- Reflection **getDeclaringClass()** giúp tìm owner; **getField** có thể thấy field inherited, còn **getDeclaredField** chỉ thấy field tự khai báo.
- Dùng tên declaring class khi viết code giúp tránh nhầm lẫn về trạng thái và thứ tự initialization.

### Tài liệu tham khảo

- **JLS §12.4.1, When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1
- **JLS §4.12.4, final Variables / Constant Variables:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4
- **JLS §15.11.1, Field Access Using a Primary:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.11.1
- **JLS §8.3.1.1, static Fields:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.1.1
- **Java SE 21 reflection Field API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html
