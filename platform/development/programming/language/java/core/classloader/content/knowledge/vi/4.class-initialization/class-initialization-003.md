# Các thao tác chủ động kích hoạt khởi tạo lớp và interface trong Java

## 1. Khởi tạo là giai đoạn nào?

Khi nói JVM **khởi tạo lớp (*class initialization*)**, ta đang nói đến giai đoạn thực thi mã khởi tạo các biến `static` và các khối `static { … }` của một lớp hoặc interface. Trình biên dịch thông thường gom các bước khởi tạo này vào phương thức khởi tạo lớp đặc biệt `<clinit>` trong bytecode; không phải lớp nào cũng cần một `<clinit>`. Giai đoạn này khác với:

- **Loading:** tìm/đọc biểu diễn lớp và tạo đối tượng `Class` tương ứng.
- **Linking:** bao gồm verification, preparation và resolution (có thể được thực hiện theo thời điểm phù hợp). Preparation cấp bộ nhớ cho biến `static` và thiết lập giá trị mặc định. Giá trị từ thuộc tính `ConstantValue` được gán trong **initialization, trước `<clinit>`**, theo JVMS §5.5.
- **Initialization:** thực thi các trình khởi tạo `static` có tác dụng runtime theo thứ tự khai báo, và bảo đảm các quan hệ khởi tạo cần thiết với kiểu cha.

Một lớp đã được *load* hoặc *link* **chưa chắc đã được initialize**. JVM có thể nạp thông tin kiểu trước, rồi hoãn việc chạy mã `static` cho đến khi chương trình thực sự dùng kiểu theo một trong những cách được đặc tả coi là **chủ động sử dụng (*active use*)**.

Trong một JVM, với một lớp cụ thể được định danh bởi **tên nhị phân cùng defining class loader**, việc khởi tạo thành công được thực hiện một lần. Nhiều luồng cùng kích hoạt lớp đó được JVM phối hợp đồng bộ; lần dùng sau không chạy lại các khối `static`.

## 2. Bốn thao tác bytecode chủ yếu buộc JVM khởi tạo

Ở mức JVM, bốn chỉ thị quan trọng nhất là `new`, `getstatic`, `putstatic` và `invokestatic`. Khi chỉ thị được thực thi và lớp/interface đích chưa được khởi tạo, JVM phải thực hiện khởi tạo trước khi thao tác có thể tiếp tục (sau các bước loading/linking cần thiết).

| Chỉ thị JVM | Cách dùng Java thường gặp | Kiểu thực sự được khởi tạo | Ghi nhớ |
| --- | --- | --- | --- |
| `new` | `new Customer()` | Lớp `Customer` được tạo đối tượng, cùng các kiểu cha bắt buộc | Việc khai báo biến tham chiếu đơn thuần không tương đương tạo đối tượng. |
| `getstatic` | `Customer.total` | Lớp/interface **khai báo** trường `static` được resolve | Đọc trường không phải *constant variable* kích hoạt khởi tạo; hằng compile-time thường được inline nên không phát sinh `getstatic`. |
| `putstatic` | `Customer.total = 10` | Lớp/interface **khai báo** trường `static` được resolve | JVM khởi tạo kiểu trước khi phép ghi `static` bên ngoài chạy. |
| `invokestatic` | `Customer.refresh()` | Lớp/interface **khai báo** phương thức `static` được resolve | Khởi tạo diễn ra trước khi thân phương thức `static` được gọi. |

Ví dụ với:

~~~java
class Counter {
    static int count = initialize();
    static int initialize() {
        System.out.println("Counter initialized");
        return 1;
    }
    static void reset() { count = 0; }
}
~~~

Lần đầu thực hiện `Counter.count`, `Counter.count = 9` hoặc `Counter.reset()` sẽ khởi tạo `Counter` trước, nếu kiểu đó chưa được khởi tạo. Nếu chạy lần lượt cả ba thao tác thì thông điệp khởi tạo chỉ xuất hiện một lần. Đoạn trên là lớp minh họa để ghép vào chương trình; ví dụ có đầy đủ `main` và kết quả xác định nằm ở phần 6.

**Chú ý về đích thực sự:** trong `Child.inheritedField`, trường có thể được khai báo trong `Parent`; khi đó chính `Parent` được khởi tạo do phép truy cập trường, còn `Child` không nhất thiết được khởi tạo. Quy tắc tương tự áp dụng với phương thức `static` kế thừa: xét kiểu **khai báo thành viên đã resolve**, không chỉ cách viết bên trái dấu chấm.

### 2.1. `new`: tạo đối tượng lớp

`new Account()` là active use của lớp `Account`. Trước khi đối tượng được tạo theo cách thông thường, JVM phải bảo đảm `Account` đã khởi tạo; nếu lớp có superclass chưa khởi tạo, superclass được khởi tạo trước. Sau đó mới tới logic instance initializer và constructor.

Phân biệt rõ:

- `Account account;` chỉ khai báo biến.
- `Account account = null;` chỉ gán tham chiếu `null`.
- `Account[] accounts = new Account[3];` tạo **array object**, không tự làm khởi tạo lớp phần tử `Account`.
- `new Account()` mới trực tiếp kích hoạt khởi tạo `Account`.

Không suy ra rằng JVM buộc phải khởi tạo mọi lớp được nhắc tên trong một tệp source.

### 2.2. `getstatic`: đọc trường `static` không phải hằng compile-time

Ví dụ:

~~~java
static final int MAX_SIZE = 64;                   // constant variable
static final String PREFIX = "ID-";             // constant variable
static final int PORT = Integer.parseInt("8080"); // giá trị tính ở runtime
static final Integer BOXED = 64;                  // không phải constant variable
static int counter = 1;
~~~

Trong Java, *constant variable* là biến `final` có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng **constant expression**. Biểu thức đọc `MAX_SIZE` hoặc `PREFIX` từ nơi khác thường được biên dịch thành chính giá trị hằng; việc đọc đó **không kích hoạt khởi tạo** lớp khai báo hằng.

Ngược lại, `PORT`, `BOXED` và `counter` không phải constant variable. Dù `PORT` và `BOXED` cũng có `final`, đọc các trường này có thể phát sinh `getstatic` và khởi tạo lớp khai báo. Câu “truy cập mọi `static final` đều không init” là **sai**.

Vì trình biên dịch có thể inline giá trị hằng vào class file của caller, việc thay đổi hằng trong thư viện mà không biên dịch lại caller còn có thể khiến caller dùng giá trị cũ. Đây là một hệ quả của việc nhúng hằng, không phải lỗi class loader.

### 2.3. `putstatic`: ghi trường `static`

Ví dụ `Settings.enabled = true` cần lớp khai báo `enabled` đã khởi tạo trước phép ghi. Nếu trong `Settings` có `static boolean enabled = false;` thì initializer chạy trong giai đoạn khởi tạo, rồi phép gán bên ngoài mới đặt thành `true`. Không nhầm bước khởi tạo mặc định/khởi tạo nội bộ với một thao tác ghi `static` của caller.

### 2.4. `invokestatic`: gọi phương thức `static`

Ví dụ `Registry.open()` kích hoạt khởi tạo kiểu khai báo phương thức `open` trước khi thân hàm chạy. Nó đúng cả khi phương thức không truy cập trường `static` nào.

Lời gọi phương thức *instance* thông thường qua một object đã tồn tại không phải một nguyên nhân chủ động mới để khởi tạo kiểu: đối tượng của một lớp được tạo theo cách chuẩn vốn đã đòi hỏi lớp đó được khởi tạo.

## 3. Những thao tác qua reflection và MethodHandle

Ngoài cú pháp Java thông thường, một số API gọi động cũng chủ động kích hoạt khởi tạo:

| Thao tác | Kích hoạt khởi tạo? | Điều kiện/giải thích |
| --- | --- | --- |
| `Class.forName("com.example.Plugin")` | **Có** | Overload một đối số yêu cầu khởi tạo lớp được tìm thấy. |
| `Class.forName(name, true, loader)` | **Có** | `initialize=true` yêu cầu khởi tạo khi lớp chưa khởi tạo. |
| `Class.forName(name, false, loader)` | **Không chỉ bởi lời gọi này** | Tìm/nạp lớp mà không yêu cầu chạy các initializer. |
| `SomeType.class` | **Không** | Lấy đối tượng `Class` không tự kích hoạt khởi tạo kiểu tương ứng. |
| `SomeType.class.getDeclaredMethods()` | **Thông thường không** | Chỉ xem metadata của kiểu; khác với gọi phương thức `static` đã tìm thấy. |
| `SomeType.class.getDeclaredConstructor().newInstance()` | **Có** | Reflection thực sự tạo instance của lớp. |
| `Method.invoke(null, …)` cho phương thức `static` | **Có** | Gọi phương thức `static` của kiểu khai báo. |
| `Field.get(null)` / `Field.set(null, value)` cho trường `static` | **Có** | Truy cập hoặc ghi trường `static` qua reflection; khác với lấy metadata `Field`. |
| `ClassLoader.loadClass(name)` theo triển khai chuẩn | **Không tự yêu cầu initialization** | Chủ yếu nạp/trả về `Class`; custom loader vẫn có thể tự chạy thêm logic. |

Ví dụ muốn khám phá plugin mà chưa chạy static initializer thì thường bắt đầu bằng `Class.forName(name, false, loader)`, sau đó cân nhắc thời điểm khởi tạo thật sự. Ngược lại, `Class.forName(name)` có thể thực thi code trong `static { … }` ngay lập tức, nên không phù hợp nếu mục tiêu chỉ là đọc metadata mà chưa kích hoạt lớp.

Ở tầng JVM, **lần gọi đầu tiên** của một `MethodHandle` được tạo từ quá trình resolve tham chiếu có các reference kind `REF_getStatic`, `REF_putStatic`, `REF_invokeStatic` hoặc `REF_newInvokeSpecial` cũng có thể kích hoạt khởi tạo kiểu đích. Phân biệt thao tác chỉ *tìm/tạo handle* với thao tác thật sự *invoke handle*; thời điểm và điều kiện chính xác được định nghĩa tại JVMS §5.5. Khi gọi bootstrap method của `invokedynamic`, việc thực thi bootstrap đó cũng phải tuân thủ quy tắc khởi tạo tương ứng.

Ngoài ra, JVM khởi tạo lớp được chọn làm điểm bắt đầu chương trình trước khi gọi `main`, và một số lời gọi JNI/phần phản chiếu từ native code cũng có thể yêu cầu khởi tạo. Vì vậy danh sách các câu lệnh Java trong một file không phải toàn bộ đường vào của quá trình này.

## 4. Khởi tạo bắc cầu qua quan hệ kế thừa

Khi **một class** được khởi tạo, JVM bảo đảm:

1. Superclass chưa khởi tạo được khởi tạo **trước** subclass.
2. Những superinterface trong quan hệ kế thừa thích hợp **có khai báo default method** cũng được khởi tạo theo thuật toán của JVM; có thể bao gồm default method do compiler tạo.
3. Sau các bước tiên quyết, initializer `static` của lớp đang khởi tạo mới chạy.

Không được suy ra rằng **mọi interface mà một lớp `implements` đều khởi tạo ngay**. Một interface không có default method thường không phải được khởi tạo chỉ vì lớp triển khai được khởi tạo. Mặt khác, việc khởi tạo **một interface** không tự động khởi tạo tất cả superinterface của nó.

Ví dụ ý nghĩa với khai báo:

~~~java
class Parent {
    static int total = 4;
}
class Child extends Parent {
    static { System.out.println("Child initialized"); }
}
~~~

Nếu lần đầu dùng là `Child.total`, chính `Parent` khai báo trường `total` nên `Parent` được khởi tạo, nhưng `Child` **không bị khởi tạo chỉ vì cú pháp `Child.total`**. Nếu sau đó `new Child()`, `Child` mới được khởi tạo; `Parent` không khởi tạo lần hai.

Nguyên tắc *only the declaring type* cũng áp dụng cho việc đọc trường `static` của interface qua tên của subinterface hoặc lớp triển khai. Khi làm bài tập, hãy xác định nơi thành viên được **khai báo thực sự** rồi mới kết luận kiểu nào chạy `<clinit>`.

## 5. Những trường hợp tưởng là active use nhưng không phải

| Hành động | Có khởi tạo `Target` chỉ từ hành động đó không? | Vì sao? |
| --- | --- | --- |
| `Target t = null;` | Không | Chỉ tạo/gán tham chiếu. |
| `Target.class` | Không | Có `Class` object không đồng nghĩa với chạy static initializer. |
| `new Target[5]` | Không | Tạo array của tham chiếu, không tạo `Target` instance. |
| `obj instanceof Target` hoặc `(Target) obj` | Không | Thử/ép kiểu không phải một trong bốn lệnh active initialization chính. |
| `ClassLoader.loadClass("Target")` | Không theo hợp đồng loadClass chuẩn | Loading khác initialization. |
| Đọc `Target.CONST` khi `CONST` là constant variable | Không | Giá trị thường được chèn ngay vào bytecode bên gọi. |
| Lấy `Field`/`Method` metadata qua reflection | Không chỉ vì lấy metadata | Việc đọc/ghi trường hoặc invoke phương thức static sau đó mới là trường hợp kích hoạt. |
| Đọc `Child.parentField` kế thừa từ `Parent` | Không đối với `Child` | Chỉ kiểu thực sự khai báo trường là đích khởi tạo của `getstatic`. |

Kết luận “không” ở bảng này là **đối với chính thao tác được xét**. Các mã chạy xung quanh, API bổ sung, hoặc cơ chế custom class loader vẫn có thể tạo hiệu ứng phụ và tự khởi tạo lớp trong lúc xử lý. Một lớp cũng có thể đã được khởi tạo trước đó từ thao tác khác.

## 6. Thí nghiệm Java 17+ kiểm chứng các trường hợp

Lưu tệp **`ActiveInitDemo.java`** sau ở một thư mục riêng, chạy bằng JDK 17 trở lên. Ví dụ đặt tất cả kiểu trợ giúp vào một lớp bên ngoài để có thể biên dịch và chạy độc lập.

~~~java
public class ActiveInitDemo {
    static class Constants {
        static { System.out.println("init Constants"); }
        static final int COMPILE_TIME = 7;
        static final int RUNTIME = Integer.parseInt("9");
    }

    static class OnWrite {
        static { System.out.println("init OnWrite"); }
        static int count = 1;
    }

    static class OnCall {
        static { System.out.println("init OnCall"); }
        static void ping() { System.out.println("ping"); }
    }

    static class Parent {
        static { System.out.println("init Parent"); }
        static int inherited = 4;
    }

    static class Child extends Parent {
        static { System.out.println("init Child"); }
    }

    interface WithDefault {
        int MARKER = announce();
        static int announce() {
            System.out.println("init WithDefault");
            return 1;
        }
        default void action() {}
    }

    static class ImplementsDefault implements WithDefault {
        static { System.out.println("init ImplementsDefault"); }
    }

    static class Reflective {
        static { System.out.println("init Reflective"); }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. passive");
        Class<?> type = Constants.class;
        System.out.println("constant=" + Constants.COMPILE_TIME);
        Class.forName(type.getName(), false, type.getClassLoader());

        System.out.println("2. getstatic");
        System.out.println("runtime=" + Constants.RUNTIME);

        System.out.println("3. putstatic");
        OnWrite.count = 5;
        System.out.println("count=" + OnWrite.count);

        System.out.println("4. invokestatic");
        OnCall.ping();

        System.out.println("5. inherited static");
        System.out.println("inherited=" + Child.inherited);

        System.out.println("6. new Child");
        new Child();

        System.out.println("7. new ImplementsDefault");
        new ImplementsDefault();

        System.out.println("8. reflection");
        Class.forName(Reflective.class.getName());
        System.out.println("done");
    }
}
~~~

Chạy trong thư mục chứa source:

~~~bash
javac ActiveInitDemo.java
java ActiveInitDemo
~~~

Kết quả stdout (đã chạy và đối chiếu):

~~~text
1. passive
constant=7
2. getstatic
init Constants
runtime=9
3. putstatic
init OnWrite
count=5
4. invokestatic
init OnCall
ping
5. inherited static
init Parent
inherited=4
6. new Child
init Child
7. new ImplementsDefault
init WithDefault
init ImplementsDefault
8. reflection
init Reflective
done
~~~

**Đọc kết quả theo trình tự:**

1. Phần `passive` lấy `Constants.class`, đọc hằng `COMPILE_TIME` và dùng `Class.forName(..., false, ...)`. Không dòng nào in `init Constants`.
2. Đọc `Constants.RUNTIME` (một `static final int` *không* phải constant variable) buộc khởi tạo `Constants`; initializer in `init Constants` trước khi mã `main` in giá trị `9`.
3. Ghi `OnWrite.count = 5` buộc khởi tạo `OnWrite` trước; giá trị `count` sau đó là `5`. Lần đọc tiếp không chạy lại initializer.
4. Gọi `OnCall.ping()` buộc khởi tạo `OnCall` rồi mới in `ping`.
5. Truy cập `Child.inherited` khởi tạo `Parent`, vì trường đó khai báo tại `Parent`. Nó **chưa** in `init Child`.
6. `new Child()` mới khởi tạo `Child`; `Parent` đã khởi tạo nên không in lần hai.
7. `ImplementsDefault` có superinterface `WithDefault` khai báo default method `action()`. JVM khởi tạo `WithDefault` trước `ImplementsDefault`, cho thấy đây là quy tắc khởi tạo phụ thuộc khi khởi tạo class.
8. `Class.forName(Reflective.class.getName())` yêu cầu khởi tạo `Reflective`, vì vậy thông điệp xuất hiện trước `done`.

Trong ví dụ trên, các lớp phụ trợ lần đầu được dùng theo đúng thứ tự để việc quan sát độc lập và dễ kiểm chứng. Nếu đổi thứ tự các thao tác, một lớp đã được khởi tạo ở bước trước sẽ không chạy lại initializer, khiến đầu ra khác.

## 7. Quy trình khởi tạo và lỗi dễ gặp

Khi một thao tác đòi hỏi khởi tạo kiểu `T`, JVM dùng trạng thái khởi tạo của chính kiểu đó để bảo đảm hành vi đúng cho nhiều luồng:

~~~text
Thao tác active use đối với T
          |
          v
T đã khởi tạo thành công? ---- Có ----> Tiếp tục thao tác
          |
         Chưa
          |
          v
T đang được luồng khác khởi tạo?
          |                           \
         Có                           Không
          |                             |
          v                             v
Chờ kết quả theo quy tắc JVM    Khởi tạo kiểu cha liên quan
                                        |
                                        v
                                Chạy initializer của T
                                        |
                            +-----------+-----------+
                            |                       |
                         Thành công               Thất bại
                            |                       |
                            v                       v
                       Đánh dấu xong        T ở trạng thái lỗi
~~~

Chi tiết thuật toán đồng bộ và xử lý khởi tạo đệ quy nằm trong JLS §12.4.2 và JVMS §5.5; sơ đồ chỉ nêu những giai đoạn cần hiểu.

- **Khối `static` ném exception:** khi initializer thất bại, JVM đánh dấu kiểu ở trạng thái lỗi. Lần khởi tạo gây lỗi có thể ném `ExceptionInInitializerError` (nếu nguyên nhân là ngoại lệ không phải `Error`); lần dùng sau có thể nhận `NoClassDefFoundError` vì lớp đã không thể khởi tạo. Đó là lỗi *initialization*, khác với lỗi class file không tìm thấy.
- **Dùng biến `static` trong chu trình khởi tạo:** một initializer có thể gọi sang kiểu khác rồi vòng lại kiểu ban đầu. Luồng đang khởi tạo có thể quan sát trường chưa được gán giá trị cuối cùng, ví dụ `0` hoặc `null`; tránh thiết kế các trình khởi tạo phụ thuộc vòng.
- **I/O, network hoặc logic nặng trong `static`:** việc chỉ gọi `Class.forName(name)` hay một method `static` đơn giản có thể phát sinh công việc ngoài ý muốn hoặc failure tại thời điểm runtime; hãy giữ side effect có kiểm soát.
- **Đo thời điểm bằng log loading:** `-verbose:class` hoặc `-Xlog:class+load=info` cho biết class loading, không chứng minh được thời điểm chạy `<clinit>`. Dùng thông điệp trong initializer hoặc công cụ chuyên dụng để quan sát initialization.
- **Hiểu sai về hằng:** chỉ *constant variable* theo JLS mới có quy tắc đọc không khởi tạo như đã mô tả. Có `static final` không đồng nghĩa với compile-time constant.
- **Hiểu sai đích khởi tạo qua kế thừa:** hãy xác định nơi member được khai báo hoặc loại lớp đang thực sự được tạo, không suy đoán từ tên phía trước dấu chấm.

## 8. Checklist suy luận một biểu thức có kích hoạt khởi tạo không

Khi gặp một biểu thức Java hoặc đoạn bytecode, lần lượt xét:

1. JVM có đang thực thi `new`, `getstatic`, `putstatic` hoặc `invokestatic` không? Nếu là truy cập hằng `static final`, cần kiểm tra xem trình biên dịch có dùng literal inline thay vì `getstatic` hay không.
2. Nếu là truy cập thành viên `static`, **lớp/interface nào khai báo trường hoặc phương thức sau khi resolve**?
3. Nếu là reflection, đang chỉ đọc metadata hay thật sự yêu cầu initialization, tạo instance, gọi phương thức hoặc đọc/ghi trường `static`? Overload `Class.forName` có đối số `initialize` bằng gì?
4. Nếu là `MethodHandle`, đang lấy handle hay đã invoke handle thuộc reference kind có thể kích hoạt?
5. Kiểu đích đã khởi tạo chưa? Nếu đã xong, initializer không chạy thêm lần nữa. Nếu chưa, superclass và các superinterface có default method liên quan có thể phải khởi tạo trước.
6. Đừng suy đoán chỉ từ việc một class đã được load, có `Class` object, được nói đến trong signature, hoặc có một mảng của kiểu đó.

**Tự kiểm tra:** Hai câu lệnh `Plugin.class.getDeclaredMethods()` và `Class.forName("com.example.Plugin")` có cùng tác động với static initializer của `Plugin` không? **Không.** Trường hợp đầu chỉ truy vấn metadata; trường hợp sau (với overload một tham số và tên lớp hợp lệ) yêu cầu khởi tạo nếu `Plugin` chưa khởi tạo.

## Tài liệu chuẩn

- [JLS Java SE 21, §12.4.1 – When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1): liệt kê active use ở mức ngôn ngữ, hằng compile-time, class/interface, default methods và reflection.
- [JLS Java SE 21, §12.4.2 – Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.2): đồng bộ, khởi tạo lặp và xử lý thất bại.
- [JVMS Java SE 21, §5.5 – Initialization](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5): `new`, `getstatic`, `putstatic`, `invokestatic`, `MethodHandle` và hành vi JVM.
- [JDK 21, Class.forName](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): phân biệt `initialize=true` và `false`.
